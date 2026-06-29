#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EXTRAS="${SAFEAI_EXTRAS:-core}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 is required. Install Python 3.9+ and rerun this script." >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("Python 3.9+ is required.")
PY

cd "$ROOT"
"$PYTHON_BIN" -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
if [ "$EXTRAS" = "core" ] || [ -z "$EXTRAS" ]; then
  python -m pip install "."
else
  python -m pip install ".[${EXTRAS}]"
fi

if [ "${SAFEAI_INSTALL_DEV:-0}" = "1" ]; then
  python -m pip install ".[dev]"
fi

echo
echo "safeai installed in $ROOT/.venv"
echo "Activate it with:"
echo "  source .venv/bin/activate"
echo
safeai doctor
