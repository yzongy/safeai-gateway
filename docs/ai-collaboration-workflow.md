# AI collaboration workflow

Use this workflow before asking Codex or another AI assistant to read company material.

## 1. Prepare

Run:

```bash
PYTHONPATH=tools/ai_collab_gateway/src python3 -m safeai doctor
PYTHONPATH=tools/ai_collab_gateway/src python3 -m safeai prepare <file-or-folder>
```

If `prepare` prints `blocked: true`, do not send anything to AI. Open the report and fix the cause first. Common causes are API keys, private keys, passwords, scanned PDFs without OCR, and unsupported file formats.

## 2. Share only the bundle

Use the printed `bundle:` file as the AI input. The bundle has stable placeholders like `[SAFEAI_PERSON_0001]`, so the assistant can reason across the document without seeing the real person, company, or contract number.

## 3. Keep the report local

The report is for audit. It shows what was found and where, but not the raw values. It is still internal metadata, so keep it with the project.

## 4. Restore only when needed

If AI output must be converted back to the original entity names:

```bash
PYTHONPATH=tools/ai_collab_gateway/src python3 -m safeai restore .safeai/out/<run_id>/bundle.md --run <run_id>
```

`restore` writes a new file. It does not overwrite the sanitized bundle.

## 5. Add dictionaries

For better results, put local dictionaries in:

- `tools/ai_collab_gateway/examples/dictionaries/employees.csv`
- `tools/ai_collab_gateway/examples/dictionaries/customers.csv`
- `tools/ai_collab_gateway/examples/dictionaries/projects.csv`

Each file should have a header row and one term per line. Do not commit real employee or customer dictionaries unless the repository is allowed to contain that data.
