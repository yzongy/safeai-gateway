from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from pathlib import Path
from typing import Dict, List

from .policy import load_policy
from .vault import VAULT_FILE


OPTIONAL_MODULES = {
    "yaml": "PyYAML policy parsing",
    "openpyxl": "xlsx extraction",
    "docx": "enhanced docx extraction",
    "pptx": "enhanced pptx extraction",
    "fitz": "PDF extraction via PyMuPDF",
    "PIL": "image loading",
    "pytesseract": "OCR bridge",
    "cryptography": "recommended vault crypto backend",
    "keyring": "recommended OS keychain integration",
    "presidio_analyzer": "optional PII engine",
    "presidio_anonymizer": "optional anonymizer engine",
    "detect_secrets": "optional Python secret scanner",
}


def run_doctor(root: Path = Path.cwd()) -> Dict[str, object]:
    modules = {name: importlib.util.find_spec(name) is not None for name in OPTIONAL_MODULES}
    commands = {name: shutil.which(name) is not None for name in ("tesseract", "gitleaks", "pdftotext", "textutil", "antiword", "catdoc", "soffice")}
    policy = load_policy("strict-ai")
    vault_path = root / ".safeai" / "vault" / VAULT_FILE
    return {
        "title": "safeai doctor",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "policy": policy.name,
        "modules": modules,
        "commands": commands,
        "vault_exists": vault_path.exists(),
        "notes": _notes(modules, commands),
    }


def format_doctor(info: Dict[str, object]) -> str:
    lines = [str(info["title"]), f"python: {info['python']}", f"platform: {info['platform']}", f"policy: {info['policy']}"]
    lines.append("modules:")
    for name, present in sorted(info["modules"].items()):
        lines.append(f"  {'ok' if present else 'missing'} {name}")
    lines.append("commands:")
    for name, present in sorted(info["commands"].items()):
        lines.append(f"  {'ok' if present else 'missing'} {name}")
    lines.append(f"vault_exists: {info['vault_exists']}")
    for note in info["notes"]:
        lines.append(f"note: {note}")
    return "\n".join(lines)


def _notes(modules: Dict[str, bool], commands: Dict[str, bool]) -> List[str]:
    notes: List[str] = []
    if not modules.get("cryptography"):
        notes.append("Install the security or all extra for the Fernet vault backend: python3 -m pip install 'safeai-gateway[security]'.")
    if not modules.get("keyring"):
        notes.append("Install the security or all extra to store vault keys in the OS keychain when available.")
    if not modules.get("presidio_analyzer"):
        notes.append("Install Presidio for stronger NER; core regex and dictionary detectors are active.")
    if not commands.get("tesseract"):
        notes.append("Install Tesseract before preparing scanned PDFs or images.")
    if not any(commands.get(name) for name in ("textutil", "antiword", "catdoc", "soffice")):
        notes.append("Install macOS textutil, LibreOffice, antiword, or catdoc before preparing legacy .doc files.")
    return notes
