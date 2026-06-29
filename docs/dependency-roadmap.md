# Dependency roadmap

`safeai` installs its core Python dependencies automatically through `pip`. The default dependency set stays light so a fresh clone installs quickly. The `all` extra installs the heavier local document/OCR/security stack:

- `openpyxl`, `python-docx`, and `python-pptx`: Office extraction.
- `PyMuPDF`: PDF extraction.
- `Pillow`, `pytesseract`, and the `tesseract` binary: image and scanned PDF OCR. The Python packages install automatically; the Tesseract binary still needs the OS package manager.
- `cryptography`: Fernet vault backend.
- `keyring`: OS keychain storage for the vault master key.
- `presidio-analyzer` and `presidio-anonymizer`: add a local NER-based PII detector.
- `detect-secrets`: add a second Python secret scanner.
- `gitleaks`: optional external binary secret scanner.

Install only what the machine and compliance policy allow. The default path remains offline.
