# safeai threat model

## Assets

- Original sensitive files: contracts, HR files, finance, legal material, R&D notes, customer data.
- Secret material: API keys, cookies, JWTs, private keys, passwords, recovery codes.
- Vault mappings: token to original value mappings.
- Sanitized bundles: files intended for AI tools.
- Reports: metadata and counts used for audit.

## Trust boundaries

- Trusted: local filesystem under the user's control, the `safeai` process, local policy files, local dictionaries.
- Conditionally trusted: optional OCR and document parsing libraries installed by the user.
- Untrusted: input files, extracted text, file names, document metadata, OCR output, AI tools, web pages, MCP outputs, logs.

## Main risks and controls

- Raw value leakage in reports or logs. Reports only contain entity type, action, locator, source id, and file hash. Tests assert synthetic raw values do not appear in reports.
- Secret leakage into AI bundles. Secret-like findings are `fail` actions. `prepare` does not write `bundle.md` when any fail finding exists.
- Prompt injection inside source documents. `safeai` treats all document text as data. It does not execute document instructions and does not fetch remote content.
- Vault disclosure. The vault file is authenticated and encrypted. File permissions are set to `0700` for the vault directory and `0600` for vault files. For stronger key isolation, install `keyring` or set a passphrase outside the repository.
- Symlink escape. Directory traversal skips hidden folders and `.git`; symlink targets outside the run root are ignored.
- OCR miss. Scanned PDFs and images require local OCR. If OCR is missing, `prepare` fails closed for those files.

## Current limits

- The built-in vault backend is portable and tested, but it is not a substitute for an audited cryptography stack. `doctor` recommends `cryptography` and `keyring`.
- Presidio is optional in this version. Core detection is strong enough for common Chinese PII and secrets, but it will miss some names and domain-specific entities without dictionaries.
- Redacted Office/PDF originals are not guaranteed. The canonical AI artifact is the sanitized Markdown bundle.

## Incident response

If a raw value appears where it should not:

1. Stop using the generated bundle.
2. Run `safeai scan` on the output directory and report file.
3. Delete the affected `.safeai/out/<run_id>` directory.
4. Rotate or revoke any exposed secret.
5. Add a regression fixture with the leaked pattern before changing detection logic.
