from safeai.vault import Vault


def test_vault_encrypts_mapping_file_and_restores_tokens(tmp_path):
    vault = Vault(tmp_path / "vault")
    token = vault.token_for("PERSON", "张三", run_id="run-1")
    vault.save()

    raw = (tmp_path / "vault" / "safeai.sqlite.enc").read_bytes()
    assert "张三".encode("utf-8") not in raw
    assert token.startswith("[SAFEAI_PERSON_")

    reopened = Vault(tmp_path / "vault")
    assert reopened.restore_text(f"hello {token}") == "hello 张三"
