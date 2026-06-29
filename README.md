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

For Codex integration, use Python 3.10+ for the MCP server:

```bash
python3.12 -m pip install "safeai-gateway[codex] @ git+https://github.com/yzongy/safeai-gateway.git"
safeai codex install --scope user
safeai codex status
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
safeai mcp --policy strict-ai
safeai codex install --scope user --policy strict-ai --python auto --runtime-extra all
safeai codex status --scope user
safeai codex uninstall --scope user
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
- `PERSON`, `ORG`, `PROJECT`, `CUSTOMER`, `SUPPLIER`, `CONTRACT_ID`, `SAMPLE_ID`: reversible tokens such as `[SAFEAI_PERSON_0001]`.
- `PHONE`, `EMAIL`, `ID_CARD`, `BANK_CARD`: redacted or masked.
- `ADDRESS`, `DATE`, `MONEY`: generalized, month-only, or bucketed.

The core detector uses local rules, Chinese PII patterns, secret signatures, and optional dictionaries. If Presidio is installed later, it can be added as a stronger local NER layer without changing the gateway contract.

## Use with Codex

`safeai` can register itself as a local Codex MCP server and install a global skill named `safeai-codex-gateway`. After installation, Codex has tools for `safeai_doctor`, `safeai_scan`, `safeai_prepare`, and `safeai_restore`.

Run:

```bash
safeai codex install --scope user --policy strict-ai --python auto
```

The installer writes:

- `~/.codex/skills/safeai-codex-gateway/SKILL.md`
- `~/.codex/skills/safeai-codex-gateway/agents/openai.yaml`
- a managed `[mcp_servers.safeai]` block in `~/.codex/config.toml`
- a short global rule in `~/.codex/AGENTS.md`

It creates backups before editing existing Codex files. It does not print or rewrite existing provider tokens or MCP credentials.

If the selected Python does not already have `safeai` and the MCP SDK installed, the installer creates `~/.codex/safeai-gateway/venv` and installs the `all` extra there. Use `--runtime-extra codex` for a smaller MCP-only runtime. The MCP server in `config.toml` points to the managed runtime.

The installed skill tells Codex to handle sensitive local files this way:

1. Do not read the raw file body first.
2. Call `safeai_prepare` on the local path.
3. If `blocked=false`, read only the returned `bundle_path`.
4. If `blocked=true`, stop and report the local `report_path` plus blocked categories.

This is a Codex tool and instruction integration, not an operating-system file-access hook. If sensitive text is pasted directly into chat, Codex cannot pre-sanitize it; save the material as a local file and run it through `safeai_prepare`.

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
