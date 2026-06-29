from __future__ import annotations

import re
from typing import List, Tuple

from .models import Finding
from .vault import Vault


def redact_text(text: str, findings: List[Finding], vault: Vault, run_id: str) -> Tuple[str, List[Tuple[str, str]]]:
    replacements: List[Tuple[Finding, str]] = []
    token_pairs: List[Tuple[str, str]] = []
    for finding in findings:
        if finding.action == "fail":
            continue
        replacement = replacement_for(finding, vault, run_id)
        replacements.append((finding, replacement))
        if finding.action == "tokenize":
            token_pairs.append((replacement, finding.entity_type))

    output = text
    for finding, replacement in sorted(replacements, key=lambda item: item[0].start, reverse=True):
        output = output[: finding.start] + replacement + output[finding.end :]
    return output, token_pairs


def replacement_for(finding: Finding, vault: Vault, run_id: str) -> str:
    entity = finding.entity_type
    if finding.action == "tokenize":
        return vault.token_for(entity, finding.value, run_id=run_id)
    if finding.action == "mask":
        return f"[SAFEAI_{entity}_MASKED]"
    if finding.action == "redact":
        return f"[SAFEAI_{entity}_REDACTED]"
    if finding.action == "generalize":
        return f"[SAFEAI_{entity}_GENERALIZED]"
    if finding.action == "month_only":
        month = _month_from_value(finding.value)
        return f"[SAFEAI_DATE_{month}]" if month else "[SAFEAI_DATE_MONTH]"
    if finding.action == "bucket":
        return f"[SAFEAI_MONEY_{_money_bucket(finding.value)}]"
    return f"[SAFEAI_{entity}_REPLACED]"


def _month_from_value(value: str) -> str:
    match = re.search(r"((?:19|20)\d{2})[年/-](0?[1-9]|1[0-2])", value)
    if not match:
        return ""
    return f"{match.group(1)}-{int(match.group(2)):02d}"


def _money_bucket(value: str) -> str:
    raw = re.sub(r"[^\d.]", "", value.replace(",", ""))
    try:
        amount = float(raw)
    except ValueError:
        return "BUCKET"
    if "万" in value:
        amount *= 10000
    if amount < 1000:
        return "LT_1K"
    if amount < 10000:
        return "1K_10K"
    if amount < 100000:
        return "10K_100K"
    if amount < 1000000:
        return "100K_1M"
    return "GT_1M"
