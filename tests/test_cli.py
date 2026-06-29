import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(cwd, *args):
    project_src = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_src)
    return subprocess.run(
        [sys.executable, "-m", "safeai", *args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_cli_doctor_scan_prepare_and_restore(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("李四在测试公司，电话13900001111，金额5000元。", encoding="utf-8")

    doctor = run_cli(tmp_path, "doctor")
    assert doctor.returncode == 0
    assert "safeai doctor" in doctor.stdout

    scan = run_cli(tmp_path, "scan", str(source))
    assert scan.returncode == 0
    assert "report:" in scan.stdout

    prepared = run_cli(tmp_path, "prepare", str(source))
    assert prepared.returncode == 0
    assert "bundle:" in prepared.stdout
    bundle_path = prepared.stdout.split("bundle:", 1)[1].splitlines()[0].strip()
    assert bundle_path

    report_path = prepared.stdout.split("report:", 1)[1].splitlines()[0].strip()
    report = json.loads(open(report_path, encoding="utf-8").read())

    restored = run_cli(tmp_path, "restore", bundle_path, "--run", report["run_id"])
    assert restored.returncode == 0
    assert "restored:" in restored.stdout
