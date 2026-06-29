from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .codex import install_codex_gateway, status_codex_gateway, uninstall_codex_gateway
from .doctor import format_doctor, run_doctor
from .mcp_server import run_mcp_server
from .pipeline import prepare, restore, scan
from .vault import Vault


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="safeai", description="Local offline redaction gateway for AI collaboration.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check local dependencies, OCR, vault, and policy readiness.")

    scan_parser = sub.add_parser("scan", help="Detect sensitive material without writing a vault or AI bundle.")
    scan_parser.add_argument("paths", nargs="+")
    scan_parser.add_argument("--policy", default="strict-ai")
    scan_parser.add_argument("--out", default=None)

    prepare_parser = sub.add_parser("prepare", help="Create a sanitized AI bundle if no fail-on-secret finding exists.")
    prepare_parser.add_argument("paths", nargs="+")
    prepare_parser.add_argument("--policy", default="strict-ai")
    prepare_parser.add_argument("--out", default=None)

    restore_parser = sub.add_parser("restore", help="Restore safeai tokens from the local encrypted vault into a new file.")
    restore_parser.add_argument("sanitized_file")
    restore_parser.add_argument("--run", required=True, dest="run_id")
    restore_parser.add_argument("--out", default=None)

    vault_parser = sub.add_parser("vault", help="Manage local token mapping vault.")
    vault_sub = vault_parser.add_subparsers(dest="vault_command", required=True)
    vault_sub.add_parser("status")
    vault_sub.add_parser("unlock")
    vault_sub.add_parser("rotate-key")
    purge = vault_sub.add_parser("purge-run")
    purge.add_argument("run_id")

    mcp_parser = sub.add_parser("mcp", help="Start the safeai Codex MCP server over stdio.")
    mcp_parser.add_argument("--policy", default="strict-ai")

    codex_parser = sub.add_parser("codex", help="Install, inspect, or remove Codex integration.")
    codex_sub = codex_parser.add_subparsers(dest="codex_command", required=True)
    codex_install = codex_sub.add_parser("install")
    codex_install.add_argument("--scope", default="user", choices=["user"])
    codex_install.add_argument("--policy", default="strict-ai")
    codex_install.add_argument("--python", default="auto")
    codex_install.add_argument("--runtime-extra", default="all", choices=["all", "codex"])
    codex_install.add_argument("--dry-run", action="store_true")
    codex_status = codex_sub.add_parser("status")
    codex_status.add_argument("--scope", default="user", choices=["user"])
    codex_uninstall = codex_sub.add_parser("uninstall")
    codex_uninstall.add_argument("--scope", default="user", choices=["user"])

    args = parser.parse_args(argv)
    if args.command == "doctor":
        print(format_doctor(run_doctor(Path.cwd())))
        return 0
    if args.command == "scan":
        result = scan([Path(item) for item in args.paths], policy=args.policy, output_dir=Path(args.out) if args.out else None)
        _print_result(result, include_bundle=False)
        return 2 if result.blocked else 0
    if args.command == "prepare":
        result = prepare([Path(item) for item in args.paths], policy=args.policy, output_dir=Path(args.out) if args.out else None)
        _print_result(result, include_bundle=not result.blocked)
        return 2 if result.blocked else 0
    if args.command == "restore":
        result = restore(Path(args.sanitized_file), run_id=args.run_id, output_path=Path(args.out) if args.out else None)
        print(f"restored: {result.output_path}")
        return 0
    if args.command == "vault":
        return _vault(args)
    if args.command == "mcp":
        return run_mcp_server(default_policy=args.policy)
    if args.command == "codex":
        return _codex(args)
    return 1


def _print_result(result, include_bundle: bool) -> None:
    print(f"run_id: {result.run_id}")
    print(f"blocked: {str(result.blocked).lower()}")
    if include_bundle:
        print(f"bundle: {result.bundle_path}")
    print(f"report: {result.report_path}")


def _vault(args) -> int:
    vault = Vault(Path.cwd() / ".safeai" / "vault")
    if args.vault_command == "status":
        print(json.dumps(vault.status(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.vault_command == "unlock":
        print("vault: unlocked")
        return 0
    if args.vault_command == "rotate-key":
        vault.rotate_key()
        print("vault: key rotated")
        return 0
    if args.vault_command == "purge-run":
        removed = vault.purge_run(args.run_id)
        print(f"vault: purged {removed} entries for {args.run_id}")
        return 0
    return 1


def _codex(args) -> int:
    try:
        if args.codex_command == "install":
            result = install_codex_gateway(
                scope=args.scope,
                policy=args.policy,
                python=args.python,
                dry_run=args.dry_run,
                runtime_extra=args.runtime_extra,
            )
        elif args.codex_command == "status":
            result = status_codex_gateway(scope=args.scope)
        elif args.codex_command == "uninstall":
            result = uninstall_codex_gateway(scope=args.scope)
        else:
            return 1
    except Exception as exc:
        print(f"safeai codex: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
