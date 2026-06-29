from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from .doctor import run_doctor
from .models import RunResult
from .pipeline import prepare, restore, scan


SKILL_NAME = "safeai-codex-gateway"
CONFIG_BEGIN = "# BEGIN SAFEAI CODEX GATEWAY"
CONFIG_END = "# END SAFEAI CODEX GATEWAY"
AGENTS_BEGIN = "<!-- BEGIN SAFEAI CODEX GATEWAY -->"
AGENTS_END = "<!-- END SAFEAI CODEX GATEWAY -->"


def install_codex_gateway(
    *,
    home: Optional[Path] = None,
    scope: str = "user",
    policy: str = "strict-ai",
    python: str = "auto",
    dry_run: bool = False,
    install_runtime: bool = True,
    runtime_extra: str = "all",
) -> dict:
    codex_dir = _codex_dir(home, scope)
    config_path = codex_dir / "config.toml"
    agents_path = codex_dir / "AGENTS.md"
    skill_dir = codex_dir / "skills" / SKILL_NAME
    python_path = _select_python(python, home=home, require_310=not dry_run)
    targets = [config_path, agents_path, skill_dir / "SKILL.md", skill_dir / "agents" / "openai.yaml"]

    if dry_run:
        return {
            "dry_run": True,
            "scope": scope,
            "policy": policy,
            "python": str(python_path),
            "runtime_extra": runtime_extra,
            "would_write": [str(target) for target in targets],
        }

    codex_dir.mkdir(parents=True, exist_ok=True)
    backups = _backup_existing([config_path, agents_path])
    runtime_python = _prepare_mcp_runtime(python_path, codex_dir, runtime_extra) if install_runtime else python_path
    _write_config(config_path, runtime_python, policy)
    _write_skill(skill_dir)
    _write_agents_rule(agents_path)
    return {
        "installed": True,
        "scope": scope,
        "policy": policy,
        "python": str(runtime_python),
        "bootstrap_python": str(python_path),
        "runtime_extra": runtime_extra,
        "runtime_installed": install_runtime,
        "config_path": str(config_path),
        "skill_path": str(skill_dir),
        "agents_path": str(agents_path),
        "backups": [str(path) for path in backups],
    }


def status_codex_gateway(*, home: Optional[Path] = None, scope: str = "user") -> dict:
    codex_dir = _codex_dir(home, scope)
    config_path = codex_dir / "config.toml"
    agents_path = codex_dir / "AGENTS.md"
    skill_dir = codex_dir / "skills" / SKILL_NAME
    config_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    agents_text = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    return {
        "scope": scope,
        "config_path": str(config_path),
        "skill_path": str(skill_dir),
        "agents_path": str(agents_path),
        "config_installed": "[mcp_servers.safeai]" in config_text,
        "skill_installed": (skill_dir / "SKILL.md").exists(),
        "agents_rule_installed": SKILL_NAME in agents_text,
    }


def uninstall_codex_gateway(*, home: Optional[Path] = None, scope: str = "user") -> dict:
    codex_dir = _codex_dir(home, scope)
    config_path = codex_dir / "config.toml"
    agents_path = codex_dir / "AGENTS.md"
    skill_dir = codex_dir / "skills" / SKILL_NAME
    backups = _backup_existing([config_path, agents_path])

    if config_path.exists():
        config_path.write_text(_remove_safeai_config(config_path.read_text(encoding="utf-8")), encoding="utf-8")
    if agents_path.exists():
        agents_path.write_text(_remove_marked_block(agents_path.read_text(encoding="utf-8"), AGENTS_BEGIN, AGENTS_END), encoding="utf-8")
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
    return {
        "uninstalled": True,
        "scope": scope,
        "config_path": str(config_path),
        "skill_path": str(skill_dir),
        "agents_path": str(agents_path),
        "backups": [str(path) for path in backups],
    }


def mcp_doctor_payload(root: Optional[str] = None) -> dict:
    root_path = _resolve_root(root)
    info = run_doctor(root_path)
    return {
        "title": info["title"],
        "python": info["python"],
        "platform": info["platform"],
        "policy": info["policy"],
        "commands": info["commands"],
        "modules": info["modules"],
        "vault_exists": info["vault_exists"],
        "notes": info["notes"],
    }


def mcp_scan_payload(paths: Iterable[str], policy: str = "strict-ai", root: Optional[str] = None) -> dict:
    root_path = _resolve_root(root)
    safe_paths = _validate_paths(paths, root_path)
    with _pushd(root_path):
        result = scan(safe_paths, policy=policy)
    return _run_payload(result, include_bundle=False)


def mcp_prepare_payload(
    paths: Iterable[str],
    policy: str = "strict-ai",
    out: Optional[str] = None,
    root: Optional[str] = None,
) -> dict:
    root_path = _resolve_root(root)
    safe_paths = _validate_paths(paths, root_path)
    output_dir = _validate_optional_path(out, root_path) if out else None
    with _pushd(root_path):
        result = prepare(safe_paths, policy=policy, output_dir=output_dir)
    return _run_payload(result, include_bundle=not result.blocked)


def mcp_restore_payload(
    sanitized_file: str,
    run_id: str,
    out: Optional[str] = None,
    root: Optional[str] = None,
) -> dict:
    root_path = _resolve_root(root)
    input_path = _validate_paths([sanitized_file], root_path)[0]
    output_path = _validate_optional_path(out, root_path) if out else None
    with _pushd(root_path):
        result = restore(input_path, run_id=run_id, output_path=output_path)
    return {
        "run_id": result.run_id,
        "input_path": str(result.input_path),
        "output_path": str(result.output_path),
        "restored_tokens": result.restored_tokens,
    }


def _codex_dir(home: Optional[Path], scope: str) -> Path:
    if scope != "user":
        raise ValueError("Only --scope user is supported in this version.")
    return Path(home) / ".codex" if home else Path.home() / ".codex"


def _select_python(python: str, *, home: Optional[Path], require_310: bool = True) -> Path:
    if python != "auto":
        return Path(python).expanduser().resolve()
    candidates: List[Path] = []
    env_python = os.environ.get("SAFEAI_CODEX_PYTHON")
    if env_python:
        candidates.append(Path(env_python).expanduser())
    base_home = Path(home) if home else Path.home()
    candidates.append(base_home / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "bin" / "python3")
    for name in ("python3.12", "python3.11", "python3.10", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    if sys.version_info >= (3, 10):
        candidates.insert(0, Path(sys.executable))

    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.exists() and _python_is_310_plus(resolved):
            return resolved
    if not require_310:
        return Path(sys.executable).resolve()
    raise RuntimeError("safeai Codex MCP integration requires Python 3.10+. Install Python 3.10+ or pass --python /path/to/python.")


def _python_is_310_plus(python_path: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(python_path), "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0


def _prepare_mcp_runtime(python_path: Path, codex_dir: Path, runtime_extra: str) -> Path:
    if runtime_extra not in {"codex", "all"}:
        raise ValueError("runtime_extra must be 'codex' or 'all'.")
    if _runtime_satisfies(python_path, runtime_extra):
        return python_path

    venv_dir = codex_dir / "safeai-gateway" / "venv"
    venv_python = _venv_python(venv_dir)
    if venv_python.exists() and _runtime_satisfies(venv_python, runtime_extra):
        return venv_python
    if not venv_dir.exists():
        _run_quiet([str(python_path), "-m", "venv", str(venv_dir)], "create Codex safeai runtime")
    _run_quiet([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], "upgrade Codex safeai runtime pip")
    _run_quiet([str(venv_python), "-m", "pip", "install", _package_install_spec(runtime_extra)], "install safeai Codex runtime")
    if not _runtime_satisfies(venv_python, runtime_extra):
        raise RuntimeError("safeai Codex runtime installed, but required modules could not be imported.")
    return venv_python


def _runtime_satisfies(python_path: Path, runtime_extra: str) -> bool:
    modules = ["safeai", "mcp"]
    if runtime_extra == "all":
        modules.extend(
            [
                "openpyxl",
                "docx",
                "pptx",
                "fitz",
                "PIL",
                "pytesseract",
                "cryptography",
                "keyring",
                "presidio_analyzer",
                "presidio_anonymizer",
                "detect_secrets",
            ]
        )
    return all(_python_can_import(python_path, module) for module in modules)


def _python_can_import(python_path: Path, module: str) -> bool:
    proc = subprocess.run(
        [str(python_path), "-c", f"import importlib.util; raise SystemExit(0 if importlib.util.find_spec({module!r}) else 1)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def _venv_python(venv_dir: Path) -> Path:
    posix = venv_dir / "bin" / "python"
    if posix.exists():
        return posix
    return venv_dir / "Scripts" / "python.exe"


def _package_install_spec(extra: str) -> str:
    root = Path(__file__).resolve().parents[2]
    if (root / "pyproject.toml").exists() and (root / "src" / "safeai").exists():
        return f"{root}[{extra}]"
    return f"safeai-gateway[{extra}] @ git+https://github.com/yzongy/safeai-gateway.git"


def _run_quiet(command: List[str], action: str) -> None:
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Could not {action}; command exited with {proc.returncode}.")


def _backup_existing(paths: Iterable[Path]) -> List[Path]:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backups: List[Path] = []
    for path in paths:
        if path.exists():
            backup = path.with_name(f"{path.name}.safeai-backup-{stamp}")
            shutil.copy2(path, backup)
            backups.append(backup)
    return backups


def _write_config(config_path: Path, python_path: Path, policy: str) -> None:
    current = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    clean = _remove_safeai_config(current).rstrip()
    block = _safeai_config_block(python_path, policy)
    next_text = f"{clean}\n\n{block}\n" if clean else f"{block}\n"
    config_path.write_text(next_text, encoding="utf-8")


def _safeai_config_block(python_path: Path, policy: str) -> str:
    args = ["-m", "safeai", "mcp", "--policy", policy]
    return "\n".join(
        [
            CONFIG_BEGIN,
            "[mcp_servers.safeai]",
            f"command = {json.dumps(str(python_path))}",
            f"args = {json.dumps(args)}",
            "startup_timeout_sec = 30",
            "tool_timeout_sec = 120",
            CONFIG_END,
        ]
    )


def _write_skill(skill_dir: Path) -> None:
    agents_dir = skill_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_skill_markdown(), encoding="utf-8")
    (agents_dir / "openai.yaml").write_text(_skill_openai_yaml(), encoding="utf-8")


def _write_agents_rule(agents_path: Path) -> None:
    current = agents_path.read_text(encoding="utf-8") if agents_path.exists() else "# Global Codex Preferences\n"
    clean = _remove_marked_block(current, AGENTS_BEGIN, AGENTS_END).rstrip()
    rule = "\n".join(
        [
            AGENTS_BEGIN,
            f"- Use the `{SKILL_NAME}` skill before reading or processing sensitive local files. For contracts, HR, finance, legal, customer, supplier, fundraising, government application, lab R&D, sequence, project, bank-flow, or identity materials, call `safeai_prepare` first and read only the returned sanitized `bundle_path`. If `blocked=true`, stop and report only the local report path and blocked categories.",
            AGENTS_END,
        ]
    )
    agents_path.write_text(f"{clean}\n\n{rule}\n", encoding="utf-8")


def _remove_safeai_config(text: str) -> str:
    text = _remove_marked_block(text, CONFIG_BEGIN, CONFIG_END)
    pattern = re.compile(r"(?ms)^\[mcp_servers\.safeai\]\s*.*?(?=^\[|\Z)")
    cleaned = pattern.sub("", text).strip()
    return f"{cleaned}\n" if cleaned else ""


def _remove_marked_block(text: str, begin: str, end: str) -> str:
    pattern = re.compile(rf"(?ms)^\\s*{re.escape(begin)}.*?{re.escape(end)}\\s*\\n?")
    return pattern.sub("", text)


def _resolve_root(root: Optional[str]) -> Path:
    root_path = Path(root).expanduser() if root else Path.cwd()
    return root_path.resolve()


def _validate_paths(paths: Iterable[str], root: Path) -> List[Path]:
    safe_paths: List[Path] = []
    for item in paths:
        if _looks_like_url(item):
            raise ValueError("URLs are not supported by safeai MCP tools. Save the material locally first.")
        candidate = Path(item).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        _require_inside_root(resolved, root)
        safe_paths.append(resolved)
    return safe_paths


def _validate_optional_path(path: str, root: Path) -> Path:
    if _looks_like_url(path):
        raise ValueError("URLs are not supported by safeai MCP tools.")
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    _require_inside_root(resolved, root)
    return resolved


def _looks_like_url(value: str) -> bool:
    return "://" in value or value.startswith("mailto:")


def _require_inside_root(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path is outside root: {path}") from exc


@contextmanager
def _pushd(path: Path) -> Iterator[None]:
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _run_payload(result: RunResult, include_bundle: bool) -> dict:
    payload = {
        "run_id": result.run_id,
        "blocked": result.blocked,
        "report_path": str(result.report_path),
        "output_dir": str(result.output_dir),
        "finding_count": len(result.findings),
        "counts_by_entity": dict(Counter(finding.entity_type for finding in result.findings)),
        "counts_by_action": dict(Counter(finding.action for finding in result.findings)),
        "files": [
            {
                "status": item.status,
                "output_path": str(item.output_path) if item.output_path else None,
                "finding_count": item.finding_count,
                "error_code": item.error_code,
            }
            for item in result.files
        ],
    }
    if include_bundle:
        payload["bundle_path"] = str(result.bundle_path)
    return payload


def _skill_markdown() -> str:
    return """---
name: safeai-codex-gateway
description: Use before Codex reads sensitive local files. Runs the local safeai MCP gateway so Codex sees sanitized bundles instead of raw confidential material.
---

# safeai Codex gateway

Use this skill before opening, summarizing, analyzing, or transforming sensitive local files.

## Trigger

Treat a path as sensitive when it appears to contain contracts, legal material, HR, finance, customer or supplier data, fundraising files, government applications, bank-flow records, identity documents, lab R&D notes, sequence/design files, unpublished project material, or anything uncertain.

## Workflow

1. Do not read the raw file body first.
2. Call `safeai_prepare` with the local path or paths and policy `strict-ai`.
3. If the tool returns `blocked=false`, read only the returned `bundle_path`.
4. If the tool returns `blocked=true`, stop. Report the `report_path`, blocked categories, and the next local remediation step. Do not open the original file.
5. Use `safeai_restore` only when the user explicitly asks to restore placeholders into a new local file.

## Pasted text

If the user pastes sensitive material directly into chat, do not repeat it. Ask them to save it as a local file and run it through `safeai_prepare`.
"""


def _skill_openai_yaml() -> str:
    return """interface:
  display_name: "safeai Codex Gateway"
  short_description: "Run local safeai redaction before Codex reads sensitive files"
  default_prompt: "Use $safeai-codex-gateway before reading sensitive local files; call safeai_prepare and read only the sanitized bundle_path."
"""
