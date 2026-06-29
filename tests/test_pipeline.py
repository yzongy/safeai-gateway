import json
from pathlib import Path

from safeai import prepare, restore, scan


def test_scan_reports_without_writing_vault_or_raw_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source.md"
    source.write_text("张三 电话13812345678 邮箱 founder@example.com 合同HT-2026-001", encoding="utf-8")

    result = scan([source], policy="strict-ai")

    assert result.report_path.exists()
    assert not (tmp_path / ".safeai" / "vault" / "safeai.sqlite.enc").exists()
    report_text = result.report_path.read_text(encoding="utf-8")
    assert "13812345678" not in report_text
    assert "founder@example.com" not in report_text
    assert result.blocked is False


def test_prepare_blocks_ai_bundle_when_secret_is_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "secret.txt"
    source.write_text("api key sk-test_1234567890abcdef1234567890abcdef", encoding="utf-8")

    result = prepare([source], policy="strict-ai")

    assert result.blocked is True
    assert result.report_path.exists()
    assert not result.bundle_path.exists()
    assert "sk-test" not in result.report_path.read_text(encoding="utf-8")


def test_prepare_blocks_when_requested_file_cannot_be_extracted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "legacy.doc"
    source.write_text("binary-ish", encoding="utf-8")

    result = prepare([source], policy="strict-ai")

    assert result.blocked is True
    assert not result.bundle_path.exists()


def test_prepare_creates_bundle_vault_and_restore_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source.md"
    source.write_text(
        "张三代表涌源合生科技联系 founder@example.com，电话13812345678，金额人民币123456元。",
        encoding="utf-8",
    )

    prepared = prepare([source], policy="strict-ai")

    assert prepared.blocked is False
    assert prepared.bundle_path.exists()
    assert prepared.report_path.exists()
    assert (tmp_path / ".safeai" / "vault" / "safeai.sqlite.enc").exists()

    bundle = prepared.bundle_path.read_text(encoding="utf-8")
    assert "[SAFEAI_PERSON_0001]" in bundle
    assert "[SAFEAI_ORG_0001]" in bundle
    assert "张三" not in bundle
    assert "涌源合生" not in bundle
    assert "founder@example.com" not in bundle
    assert "13812345678" not in bundle

    report = json.loads(prepared.report_path.read_text(encoding="utf-8"))
    assert report["blocked"] is False
    assert "张三" not in json.dumps(report, ensure_ascii=False)

    restored = restore(prepared.bundle_path, run_id=prepared.run_id)
    assert restored.output_path.exists()
    restored_text = restored.output_path.read_text(encoding="utf-8")
    assert "张三" in restored_text
    assert "涌源合生科技" in restored_text
