# safeai gateway

`safeai` is a local pre-flight gateway for AI collaboration. Feed it files first; it writes a sanitized bundle for Codex or another assistant, keeps the originals untouched, and stores reversible token mappings in a local encrypted vault.

The tool is offline by default. It does not call an LLM, upload files, or use cloud DLP services.

## Quick start

Install directly from GitHub:

```bash
python3 -m pip install "safeai-gateway @ git+https://github.com/yzongy/safeai-gateway.git"
safeai doctor
```

For the full local document/OCR/security stack:

```bash
python3 -m pip install "safeai-gateway[all] @ git+https://github.com/yzongy/safeai-gateway.git"
```

Or clone the repo and let the installer create a virtual environment:

```bash
git clone https://github.com/yzongy/safeai-gateway.git
cd safeai-gateway
./scripts/install.sh
source .venv/bin/activate
safeai doctor
```

To install all optional Python extras from a clone:

```bash
SAFEAI_EXTRAS=all ./scripts/install.sh
```

For local development from `/Users/yzongy/Desktop/Entrepreneurship`:

```bash
PYTHONPATH=tools/ai_collab_gateway/src python3 -m safeai doctor
PYTHONPATH=tools/ai_collab_gateway/src python3 -m safeai scan path/to/file.md
PYTHONPATH=tools/ai_collab_gateway/src python3 -m safeai prepare path/to/file.md
```

When `prepare` succeeds, use the printed `bundle:` path with Codex. Do not paste the original file.

## Commands

```bash
safeai doctor
safeai scan <paths...> --policy strict-ai
safeai prepare <paths...> --policy strict-ai --out .safeai/out/<run_id>
safeai restore <sanitized-file> --run <run_id>
safeai vault status
safeai vault rotate-key
safeai vault purge-run <run_id>
```

Without installation, prefix commands with:

```bash
PYTHONPATH=tools/ai_collab_gateway/src python3 -m safeai
```

## Output

`safeai` writes everything under `.safeai/`, which is ignored by git:

- `.safeai/out/<run_id>/bundle.md`: main sanitized bundle for AI.
- `.safeai/out/<run_id>/files/`: per-file sanitized Markdown.
- `.safeai/reports/<run_id>.json`: audit report with entity types, counts, locators, and file hashes. It does not include raw sensitive values.
- `.safeai/reports/<run_id>.html`: readable copy of the JSON report.
- `.safeai/vault/safeai.sqlite.enc`: encrypted token mapping vault.

## Detection and redaction

The built-in `strict-ai` policy fails closed on secrets:

- `API_KEY`, `PRIVATE_KEY`, `PASSWORD`, `JWT`, `COOKIE`: block bundle generation.
- `PERSON`, `ORG`, `PROJECT`, `CUSTOMER`, `SUPPLIER`, `CONTRACT_ID`: reversible tokens such as `[SAFEAI_PERSON_0001]`.
- `PHONE`, `EMAIL`, `ID_CARD`, `BANK_CARD`: redacted or masked.
- `ADDRESS`, `DATE`, `MONEY`: generalized, month-only, or bucketed.

The core detector uses local rules, Chinese PII patterns, secret signatures, and optional dictionaries. If Presidio is installed later, it can be added as a stronger local NER layer without changing the gateway contract.

## Supported files

Core support:

- `.txt`, `.md`, `.csv`, `.json`
- `.docx`, `.xlsx`, `.pptx` through local XML or installed Office libraries
- `.pdf` if PyMuPDF is installed
- common images if Tesseract, Pillow, and pytesseract are installed

Unsupported files such as `.doc`, `.pages`, and archives are reported as blocked or skipped. Convert them first.

## Vault notes

The core install uses a portable local sealed-file vault with HMAC authentication. Install `safeai-gateway[security]` or `safeai-gateway[all]` to use `cryptography` for a Fernet-encrypted vault and `keyring` for OS keychain storage when available. Set `SAFEAI_VAULT_PASSPHRASE` to derive the key from a passphrase instead.

## Tests

```bash
cd tools/ai_collab_gateway
python3 -m pytest
```

The test suite uses synthetic fixtures only. It checks secret fail-closed behavior, report leakage, bundle leakage, restore round trips, CLI behavior, and vault encryption at rest.
