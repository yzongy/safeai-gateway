from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, List
from xml.etree import ElementTree

from .models import ExtractedDocument


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".log"}
CSV_EXTENSIONS = {".csv", ".tsv"}
JSON_EXTENSIONS = {".json", ".jsonl"}
LEGACY_DOC_EXTENSIONS = {".doc"}
UNSUPPORTED_EXTENSIONS = {".pages", ".zip", ".rar", ".7z", ".gz", ".tar"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


def extract_documents(paths: Iterable[Path], root: Path) -> List[ExtractedDocument]:
    root = Path(root).resolve()
    documents: List[ExtractedDocument] = []
    for path in enumerate_input_files(paths, root):
        documents.append(extract_document(path, root))
    return documents


def enumerate_input_files(paths: Iterable[Path], root: Path) -> List[Path]:
    files: List[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        path = path if path.is_absolute() else Path.cwd() / path
        if path.is_symlink() and not _is_relative_to(path.resolve(), root):
            continue
        path = path.resolve()
        if path.is_dir():
            for child in path.rglob("*"):
                if _skip_path(child):
                    continue
                if child.is_symlink() and not _is_relative_to(child.resolve(), root):
                    continue
                if child.is_file():
                    files.append(child.resolve())
        elif path.is_file() and ".git" not in set(path.parts):
            files.append(path)
    return sorted(dict.fromkeys(files))


def extract_document(path: Path, root: Path) -> ExtractedDocument:
    source_id = _source_id(path, root)
    sha = _sha256(path)
    suffix = path.suffix.lower()
    try:
        if suffix in TEXT_EXTENSIONS:
            return _ok(path, source_id, _read_text(path), "text/plain", sha)
        if suffix in CSV_EXTENSIONS:
            return _ok(path, source_id, _read_delimited(path), "text/csv", sha)
        if suffix in JSON_EXTENSIONS:
            return _ok(path, source_id, _read_json(path), "application/json", sha)
        if suffix == ".docx":
            return _ok(path, source_id, _read_docx(path), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", sha)
        if suffix == ".xlsx":
            return _ok(path, source_id, _read_xlsx(path), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", sha)
        if suffix == ".pptx":
            return _ok(path, source_id, _read_pptx(path), "application/vnd.openxmlformats-officedocument.presentationml.presentation", sha)
        if suffix in LEGACY_DOC_EXTENSIONS:
            return _read_legacy_doc(path, source_id, sha)
        if suffix == ".pdf":
            return _read_pdf(path, source_id, sha)
        if suffix in IMAGE_EXTENSIONS:
            return _read_image(path, source_id, sha)
        if suffix in UNSUPPORTED_EXTENSIONS:
            return _error(path, source_id, "unsupported_format", "Convert this file to docx, xlsx, pptx, pdf, image, or text first.", sha)
        return _error(path, source_id, "unknown_format", "Unknown file type. Add an extractor before using this file for AI collaboration.", sha)
    except Exception:
        return _error(path, source_id, "extract_failed", "Extraction failed without exposing source content.", sha)


def _ok(path: Path, source_id: str, text: str, media_type: str, sha: str) -> ExtractedDocument:
    return ExtractedDocument(path=path, source_id=source_id, text=text, status="ok", media_type=media_type, sha256=sha)


def _error(path: Path, source_id: str, code: str, message: str, sha: str) -> ExtractedDocument:
    return ExtractedDocument(path=path, source_id=source_id, text="", status="error", media_type="application/octet-stream", sha256=sha, error_code=code, error_message=message)


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def _read_delimited(path: Path) -> str:
    dialect = "excel-tab" if path.suffix.lower() == ".tsv" else "excel"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, dialect=dialect)
        return "\n".join(" | ".join(cell for cell in row) for row in reader)


def _read_json(path: Path) -> str:
    data = json.loads(_read_text(path))
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    return _xml_text(xml, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")


def _read_xlsx(path: Path) -> str:
    try:
        import openpyxl
    except Exception:
        return _read_xlsx_zip(path)
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    lines = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            values = []
            for cell in row:
                if cell.value is not None:
                    values.append(f"{cell.coordinate}={cell.value}")
            if values:
                lines.append(f"[{sheet.title}] " + " | ".join(values))
    return "\n".join(lines)


def _read_xlsx_zip(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = _xml_text(archive.read("xl/sharedStrings.xml"), "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t").splitlines()
        return "\n".join(shared)


def _read_pptx(path: Path) -> str:
    lines = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(item for item in archive.namelist() if item.startswith("ppt/slides/slide") and item.endswith(".xml")):
            text = _xml_text(archive.read(name), "{http://schemas.openxmlformats.org/drawingml/2006/main}t")
            if text:
                lines.append(f"[{Path(name).stem}]\n{text}")
    return "\n\n".join(lines)


def _read_legacy_doc(path: Path, source_id: str, sha: str) -> ExtractedDocument:
    attempted_converter = False
    for command_name, args in (
        ("textutil", ["-convert", "txt", "-stdout", str(path)]),
        ("antiword", [str(path)]),
        ("catdoc", [str(path)]),
    ):
        command = shutil.which(command_name)
        if not command:
            continue
        attempted_converter = True
        text = _run_stdout_converter([command, *args])
        if text.strip():
            return _ok(path, source_id, text, "application/msword", sha)

    soffice = shutil.which("soffice")
    if soffice:
        attempted_converter = True
        text = _read_legacy_doc_with_soffice(Path(soffice), path)
        if text.strip():
            return _ok(path, source_id, text, "application/msword", sha)

    if attempted_converter:
        return _error(path, source_id, "doc_extract_failed", "Legacy .doc conversion failed without exposing source content.", sha)

    return _error(
        path,
        source_id,
        "doc_dependency_missing",
        "Install macOS textutil, LibreOffice, antiword, or catdoc to extract legacy .doc files locally.",
        sha,
    )


def _run_stdout_converter(command: List[str]) -> str:
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60, check=False)
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", errors="replace")


def _read_legacy_doc_with_soffice(soffice: Path, path: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="safeai-doc-") as tmp:
        tmp_path = Path(tmp)
        try:
            proc = subprocess.run(
                [str(soffice), "--headless", "--convert-to", "txt:Text", "--outdir", str(tmp_path), str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
            )
        except Exception:
            return ""
        if proc.returncode != 0:
            return ""
        output = tmp_path / f"{path.stem}.txt"
        if not output.exists():
            return ""
        return _read_text(output)


def _read_pdf(path: Path, source_id: str, sha: str) -> ExtractedDocument:
    try:
        import fitz
    except Exception:
        return _error(path, source_id, "pdf_dependency_missing", "Install PyMuPDF for local PDF extraction: python3 -m pip install 'safeai-gateway[pdf]'.", sha)
    doc = fitz.open(str(path))
    text = "\n\n".join(page.get_text("text") for page in doc)
    if not text.strip():
        return _error(path, source_id, "ocr_required", "PDF appears scanned. Install Tesseract and rerun safeai doctor.", sha)
    return _ok(path, source_id, text, "application/pdf", sha)


def _read_image(path: Path, source_id: str, sha: str) -> ExtractedDocument:
    if not shutil.which("tesseract"):
        return _error(path, source_id, "ocr_dependency_missing", "Install local Tesseract OCR before preparing image files.", sha)
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return _error(path, source_id, "ocr_python_dependency_missing", "Install Pillow and pytesseract for local image OCR.", sha)
    text = pytesseract.image_to_string(Image.open(path), lang="chi_sim+eng")
    return _ok(path, source_id, text, "image/*", sha)


def _xml_text(xml: bytes, tag: str) -> str:
    root = ElementTree.fromstring(xml)
    parts = [node.text or "" for node in root.iter(tag)]
    return "\n".join(part for part in parts if part)


def _source_id(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return path.name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _skip_path(path: Path) -> bool:
    parts = set(path.parts)
    if ".git" in parts or "__pycache__" in parts:
        return True
    return any(part.startswith(".") and part not in {".", ".."} for part in path.parts)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
