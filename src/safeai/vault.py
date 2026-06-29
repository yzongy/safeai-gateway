from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Dict, Iterable, Tuple


VAULT_FILE = "safeai.sqlite.enc"
KEY_FILE = "master.key"
MAGIC = b"SAFEAI1\n"


class Vault:
    def __init__(self, vault_dir: Path):
        self.vault_dir = Path(vault_dir)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.vault_dir, 0o700)
        self.path = self.vault_dir / VAULT_FILE
        self.key = self._load_or_create_key()
        self.data = self._load()

    def token_for(self, entity_type: str, raw_value: str, run_id: str) -> str:
        identity = self._identity(entity_type, raw_value)
        entries = self.data.setdefault("entries", {})
        if identity in entries:
            token = entries[identity]["token"]
            entries[identity].setdefault("runs", [])
            if run_id not in entries[identity]["runs"]:
                entries[identity]["runs"].append(run_id)
            return token

        counters = self.data.setdefault("counters", {})
        counters[entity_type] = int(counters.get(entity_type, 0)) + 1
        token = f"[SAFEAI_{entity_type}_{counters[entity_type]:04d}]"
        entries[identity] = {"token": token, "entity_type": entity_type, "value": raw_value, "runs": [run_id]}
        return token

    def restore_text(self, text: str, run_id: str = "") -> str:
        output = text
        for entry in self.data.get("entries", {}).values():
            if run_id and run_id not in entry.get("runs", []):
                continue
            output = output.replace(entry["token"], entry["value"])
        return output

    def purge_run(self, run_id: str) -> int:
        entries = self.data.setdefault("entries", {})
        removed = 0
        for identity in list(entries):
            runs = [item for item in entries[identity].get("runs", []) if item != run_id]
            if runs:
                entries[identity]["runs"] = runs
            else:
                del entries[identity]
                removed += 1
        self.save()
        return removed

    def rotate_key(self) -> None:
        old_key_path = self.vault_dir / KEY_FILE
        if old_key_path.exists():
            old_key_path.unlink()
        self.key = self._load_or_create_key()
        self.save()

    def status(self) -> Dict[str, object]:
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "entries": len(self.data.get("entries", {})),
            "key_backend": self._key_backend(),
            "crypto_backend": "cryptography-fernet" if _fernet_available() else "portable-hmac-stream",
        }

    def save(self) -> None:
        payload = json.dumps(self.data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        encrypted = self._encrypt(payload)
        self.path.write_bytes(encrypted)
        os.chmod(self.path, 0o600)

    def _load(self) -> Dict[str, object]:
        if not self.path.exists():
            return {"version": 1, "entries": {}, "counters": {}}
        return json.loads(self._decrypt(self.path.read_bytes()).decode("utf-8"))

    def _identity(self, entity_type: str, raw_value: str) -> str:
        digest = hmac.new(_derive(self.key, b"identity"), f"{entity_type}\0{raw_value}".encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _load_or_create_key(self) -> bytes:
        passphrase = os.environ.get("SAFEAI_VAULT_PASSPHRASE")
        if passphrase:
            return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), b"safeai-vault-v1", 250_000, dklen=32)
        keyring_key = _load_or_create_keyring_key()
        if keyring_key:
            return keyring_key
        key_path = self.vault_dir / KEY_FILE
        if key_path.exists():
            return base64.urlsafe_b64decode(key_path.read_bytes())
        key = secrets.token_bytes(32)
        key_path.write_bytes(base64.urlsafe_b64encode(key))
        os.chmod(key_path, 0o600)
        return key

    def _encrypt(self, payload: bytes) -> bytes:
        if _fernet_available():
            from cryptography.fernet import Fernet

            fernet_key = base64.urlsafe_b64encode(_derive(self.key, b"fernet"))
            return MAGIC + b"FERNET\n" + Fernet(fernet_key).encrypt(payload)
        nonce = secrets.token_bytes(16)
        stream = _keystream(_derive(self.key, b"enc"), nonce, len(payload))
        cipher = _xor(payload, stream)
        body = MAGIC + nonce + cipher
        tag = hmac.new(_derive(self.key, b"mac"), body, hashlib.sha256).digest()
        return body + tag

    def _decrypt(self, blob: bytes) -> bytes:
        if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 16 + 32:
            raise ValueError("Vault file is not a safeai encrypted vault")
        if blob.startswith(MAGIC + b"FERNET\n"):
            from cryptography.fernet import Fernet

            fernet_key = base64.urlsafe_b64encode(_derive(self.key, b"fernet"))
            return Fernet(fernet_key).decrypt(blob[len(MAGIC + b"FERNET\n") :])
        body, tag = blob[:-32], blob[-32:]
        expected = hmac.new(_derive(self.key, b"mac"), body, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("Vault authentication failed")
        nonce = body[len(MAGIC) : len(MAGIC) + 16]
        cipher = body[len(MAGIC) + 16 :]
        stream = _keystream(_derive(self.key, b"enc"), nonce, len(cipher))
        return _xor(cipher, stream)

    def _key_backend(self) -> str:
        if os.environ.get("SAFEAI_VAULT_PASSPHRASE"):
            return "SAFEAI_VAULT_PASSPHRASE"
        if _keyring_available() and _keyring_has_key():
            return "system-keyring"
        return "local-key-file"


def _derive(key: bytes, label: bytes) -> bytes:
    return hmac.new(key, label, hashlib.sha256).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        chunks.append(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:length]


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _fernet_available() -> bool:
    try:
        import cryptography.fernet  # noqa: F401

        return True
    except Exception:
        return False


def _keyring_available() -> bool:
    try:
        import keyring  # noqa: F401

        return True
    except Exception:
        return False


def _keyring_has_key() -> bool:
    try:
        import keyring

        return bool(keyring.get_password("safeai-gateway", "vault-master-key"))
    except Exception:
        return False


def _load_or_create_keyring_key() -> bytes:
    try:
        import keyring

        encoded = keyring.get_password("safeai-gateway", "vault-master-key")
        if encoded:
            return base64.urlsafe_b64decode(encoded.encode("ascii"))
        key = secrets.token_bytes(32)
        keyring.set_password("safeai-gateway", "vault-master-key", base64.urlsafe_b64encode(key).decode("ascii"))
        return key
    except Exception:
        return b""
