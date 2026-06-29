import json
import os
import subprocess
import sys
from pathlib import Path

from safeai.codex import (
    install_codex_gateway,
    mcp_prepare_payload,
    mcp_restore_payload,
    mcp_scan_payload,
    status_codex_gateway,
    uninstall_codex_gateway,
)


def test_codex_install_status_and_uninstall_are_idempotent(tmp_path):
    home = tmp_path / "home"
    codex_dir = home / ".codex"
    codex_dir.mkdir(parents=True)
    config = codex_dir / "config.toml"
    config.write_text(
        'model = "gpt-test"\nprivate_config_value = "CONFIG_VALUE_SHOULD_NOT_PRINT"\n',
        encoding="utf-8",
    )
    agents = codex_dir / "AGENTS.md"
    agents.write_text("# Global Codex Preferences\n", encoding="utf-8")

    dry_run = install_codex_gateway(home=home, python="auto", dry_run=True)
    assert dry_run["dry_run"] is True
    assert "CONFIG_VALUE_SHOULD_NOT_PRINT" not in json.dumps(dry_run)
    assert "safeai" not in config.read_text(encoding="utf-8")

    installed = install_codex_gateway(home=home, python=sys.executable, dry_run=False, install_runtime=False)
    installed_again = install_codex_gateway(home=home, python=sys.executable, dry_run=False, install_runtime=False)
    assert installed["installed"] is True
    assert installed_again["installed"] is True

    text = config.read_text(encoding="utf-8")
    assert text.count("[mcp_servers.safeai]") == 1
    assert text.count("BEGIN SAFEAI CODEX GATEWAY") == 1
    assert text.count("END SAFEAI CODEX GATEWAY") == 1
    assert "CONFIG_VALUE_SHOULD_NOT_PRINT" in text
    agents_text = agents.read_text(encoding="utf-8")
    assert "safeai-codex-gateway" in agents_text
    assert agents_text.count("BEGIN SAFEAI CODEX GATEWAY") == 1
    assert agents_text.count("END SAFEAI CODEX GATEWAY") == 1
    assert (codex_dir / "skills" / "safeai-codex-gateway" / "SKILL.md").exists()
    assert (codex_dir / "skills" / "safeai-codex-gateway" / "agents" / "openai.yaml").exists()

    status = status_codex_gateway(home=home)
    assert status["config_installed"] is True
    assert status["skill_installed"] is True
    assert status["agents_rule_installed"] is True
    assert "CONFIG_VALUE_SHOULD_NOT_PRINT" not in json.dumps(status)

    removed = uninstall_codex_gateway(home=home)
    assert removed["uninstalled"] is True
    assert "[mcp_servers.safeai]" not in config.read_text(encoding="utf-8")
    assert not (codex_dir / "skills" / "safeai-codex-gateway").exists()


def test_mcp_prepare_scan_and_restore_payloads_do_not_leak_raw_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "contract.md"
    source.write_text("张三代表深蓝星河联系 founder@example.com，电话13812345678。", encoding="utf-8")

    scan_payload = mcp_scan_payload([str(source)], root=str(tmp_path))
    assert scan_payload["blocked"] is False
    assert "bundle_path" not in scan_payload

    prepare_payload = mcp_prepare_payload([str(source)], root=str(tmp_path))
    dumped = json.dumps(prepare_payload, ensure_ascii=False)
    assert prepare_payload["blocked"] is False
    assert Path(prepare_payload["bundle_path"]).exists()
    assert "张三" not in dumped
    assert "深蓝星河" not in dumped
    assert "founder@example.com" not in dumped
    assert "13812345678" not in dumped

    bundle = Path(prepare_payload["bundle_path"]).read_text(encoding="utf-8")
    assert "张三" not in bundle
    assert "founder@example.com" not in bundle

    restore_payload = mcp_restore_payload(
        prepare_payload["bundle_path"],
        run_id=prepare_payload["run_id"],
        root=str(tmp_path),
    )
    restore_dumped = json.dumps(restore_payload, ensure_ascii=False)
    assert Path(restore_payload["output_path"]).exists()
    assert "张三" not in restore_dumped
    assert "深蓝星河" not in restore_dumped


def test_mcp_payload_rejects_urls_and_paths_outside_root(tmp_path):
    inside = tmp_path / "inside.md"
    inside.write_text("safe", encoding="utf-8")
    outside = tmp_path.parent / "outside-safeai-test.md"
    outside.write_text("张三", encoding="utf-8")

    try:
        for bad in ("https://example.com/file.md", str(outside)):
            try:
                mcp_scan_payload([bad], root=str(tmp_path))
            except ValueError as exc:
                assert "outside root" in str(exc) or "URLs are not supported" in str(exc)
            else:
                raise AssertionError(f"expected ValueError for {bad}")
    finally:
        outside.unlink(missing_ok=True)


def test_safeai_mcp_fails_fast_without_mcp_sdk_on_python39():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "safeai", "mcp"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if sys.version_info < (3, 10):
        assert proc.returncode == 2
        assert "Python 3.10+" in proc.stderr
