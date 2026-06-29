from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, List

from .models import ExtractedDocument, FileResult, Finding


def write_reports(
    report_dir: Path,
    run_id: str,
    blocked: bool,
    documents: Iterable[ExtractedDocument],
    findings: List[Finding],
    files: List[FileResult],
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "run_id": run_id,
        "blocked": blocked,
        "finding_count": len(findings),
        "counts_by_entity": dict(Counter(finding.entity_type for finding in findings)),
        "counts_by_action": dict(Counter(finding.action for finding in findings)),
        "findings": [finding.to_report_dict() for finding in findings],
        "files": [
            {
                "source_id": doc.source_id,
                "status": doc.status,
                "media_type": doc.media_type,
                "sha256": doc.sha256,
                "error_code": doc.error_code,
                "error_message": doc.error_message,
            }
            for doc in documents
        ],
        "outputs": [
            {
                "source_id": item.source_id,
                "status": item.status,
                "output_path": str(item.output_path) if item.output_path else None,
                "finding_count": item.finding_count,
                "error_code": item.error_code,
                "error_message": item.error_message,
            }
            for item in files
        ],
    }
    json_path = report_dir / f"{run_id}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    html_path = report_dir / f"{run_id}.html"
    html_path.write_text(_html_report(report), encoding="utf-8")
    return json_path


def _html_report(report: dict) -> str:
    escaped = html.escape(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>safeai report {html.escape(report["run_id"])}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 920px; margin: 40px auto; line-height: 1.5; }}
    pre {{ background: #f6f8fa; border: 1px solid #d0d7de; padding: 16px; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>safeai report</h1>
  <p>Run: <code>{html.escape(report["run_id"])}</code></p>
  <p>Blocked: <strong>{html.escape(str(report["blocked"]))}</strong></p>
  <pre>{escaped}</pre>
</body>
</html>
"""
