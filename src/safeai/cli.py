from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .doctor import format_doctor, run_doctor
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
