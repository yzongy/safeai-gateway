from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .detectors import RedactionDetector
from .extractors import extract_documents
from .models import FileResult, Finding, RestoreResult, RunResult
from .policy import load_policy
from .redactor import redact_text
from .report import write_reports
from .vault import Vault


def scan(paths: Iterable[Path], policy: str = "strict-ai", output_dir: Optional[Path] = None) -> RunResult:
    return _run(paths, policy_name=policy, output_dir=output_dir, write_bundle=False)


def prepare(paths: Iterable[Path], policy: str = "strict-ai", output_dir: Optional[Path] = None) -> RunResult:
    return _run(paths, policy_name=policy, output_dir=output_dir, write_bundle=True)


def restore(path: Path, run_id: str, output_path: Optional[Path] = None) -> RestoreResult:
    root = Path.cwd()
    safeai_dir = root / ".safeai"
    vault = Vault(safeai_dir / "vault")
    input_path = Path(path)
    text = input_path.read_text(encoding="utf-8")
    restored = vault.restore_text(text, run_id=run_id)
    out = output_path or input_path.with_suffix(input_path.suffix + ".restored")
    out.write_text(restored, encoding="utf-8")
    return RestoreResult(run_id=run_id, input_path=input_path, output_path=out, restored_tokens=restored.count("[SAFEAI_"))


def _run(paths: Iterable[Path], policy_name: str, output_dir: Optional[Path], write_bundle: bool) -> RunResult:
    root = Path.cwd()
    safeai_dir = root / ".safeai"
    out_root = Path(output_dir) if output_dir else safeai_dir / "out"
    reports_dir = safeai_dir / "reports"
    run_id = _new_run_id()
    run_out = out_root if output_dir else out_root / run_id
    bundle_path = run_out / "bundle.md"
    files_dir = run_out / "files"
    policy = load_policy(policy_name)
    detector = RedactionDetector(policy, base_dir=root)
    documents = extract_documents([Path(item) for item in paths], root=root)
    vault = Vault(safeai_dir / "vault") if write_bundle else None

    all_findings: List[Finding] = []
    file_outputs: List[FileResult] = []
    redacted_by_source: Dict[str, str] = {}

    for doc in documents:
        if doc.status != "ok":
            file_outputs.append(FileResult(doc.source_id, doc.path, "error", None, 0, doc.error_code, doc.error_message))
            continue
        findings = detector.detect(doc.text, source_id=doc.source_id)
        all_findings.extend(findings)
        if write_bundle and vault is not None:
            redacted, _ = redact_text(doc.text, findings, vault, run_id)
            redacted_by_source[doc.source_id] = redacted
            file_outputs.append(FileResult(doc.source_id, doc.path, "prepared", files_dir / _safe_output_name(doc.source_id), len(findings)))
        else:
            file_outputs.append(FileResult(doc.source_id, doc.path, "scanned", None, len(findings)))

    blocked = any(finding.action == "fail" for finding in all_findings)
    if write_bundle:
        blocked = blocked or any(doc.status == "error" for doc in documents)
    else:
        blocked = blocked or any(doc.status == "error" and doc.error_code in {"ocr_required", "ocr_dependency_missing", "ocr_python_dependency_missing"} for doc in documents)

    if write_bundle and not blocked and vault is not None:
        run_out.mkdir(parents=True, exist_ok=True)
        files_dir.mkdir(parents=True, exist_ok=True)
        _write_redacted_files(files_dir, redacted_by_source, file_outputs)
        bundle = _bundle(redacted_by_source)
        second_pass = detector.detect(bundle, source_id="bundle.md")
        leaked = [finding for finding in second_pass if finding.action == "fail"]
        if leaked:
            blocked = True
            if bundle_path.exists():
                bundle_path.unlink()
            all_findings.extend(leaked)
        else:
            bundle_path.write_text(bundle, encoding="utf-8")
            vault.save()
    elif write_bundle and blocked and run_out.exists():
        shutil.rmtree(run_out)

    if not write_bundle:
        bundle_path = run_out / "bundle.md"

    report_path = write_reports(reports_dir, run_id, blocked, documents, all_findings, file_outputs)
    return RunResult(run_id=run_id, blocked=blocked, report_path=report_path, bundle_path=bundle_path, output_dir=run_out, findings=all_findings, files=file_outputs)


def _new_run_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _safe_output_name(source_id: str) -> str:
    clean = "".join(char if char.isalnum() or char in ".-_" else "_" for char in source_id)
    return clean + ".redacted.md"


def _write_redacted_files(files_dir: Path, redacted_by_source: Dict[str, str], file_outputs: List[FileResult]) -> None:
    for item in file_outputs:
        if item.output_path and item.source_id in redacted_by_source:
            item.output_path.write_text(redacted_by_source[item.source_id], encoding="utf-8")


def _bundle(redacted_by_source: Dict[str, str]) -> str:
    parts = ["# safeai sanitized bundle", ""]
    for source_id, text in sorted(redacted_by_source.items()):
        parts.append(f"## Source: {source_id}")
        parts.append("")
        parts.append(text)
        parts.append("")
    return "\n".join(parts)
