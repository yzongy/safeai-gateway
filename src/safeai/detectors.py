from __future__ import annotations

import csv
import importlib.util
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .models import Finding
from .policy import Policy


SECRET_PATTERNS: Sequence[Tuple[str, str, re.Pattern, float]] = (
    ("PRIVATE_KEY", "private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"), 1.0),
    ("JWT", "jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), 0.98),
    ("API_KEY", "openai-key", re.compile(r"\bsk-(?:proj-|test_|live_)?[A-Za-z0-9_-]{24,}\b"), 0.98),
    ("API_KEY", "aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), 0.98),
    ("API_KEY", "github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs)_[A-Za-z0-9_]{24,}\b"), 0.98),
    ("COOKIE", "cookie", re.compile(r"(?i)\b(?:set-cookie|cookie)\s*[:=]\s*[^;\n]{12,}"), 0.9),
    ("PASSWORD", "password", re.compile(r"(?i)\b(?:password|passwd|pwd|secret)\s*[:=]\s*['\"]?[^'\"\s]{8,}"), 0.9),
)

PII_PATTERNS: Sequence[Tuple[str, str, re.Pattern, float]] = (
    ("EMAIL", "email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0.95),
    ("PHONE", "cn-phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), 0.95),
    ("ID_CARD", "cn-id-card", re.compile(r"(?<![0-9A-Za-z])\d{6}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx](?![0-9A-Za-z])"), 0.95),
    ("BANK_CARD", "bank-card", re.compile(r"(?<!\d)(?:\d[ -]?){15,19}(?!\d)"), 0.72),
    ("USCC", "cn-uscc", re.compile(r"(?<![0-9A-Z])[0-9A-Z]{18}(?![0-9A-Z])"), 0.78),
    ("CONTRACT_ID", "contract-id", re.compile(r"(?<![A-Za-z0-9])(?:HT|XS|NDA|CDA|PO|SO)-?\d{4}[-A-Z0-9]{3,}(?![A-Za-z0-9])", re.I), 0.86),
    ("MONEY", "money", re.compile(r"(?:人民币|RMB|¥|\$)\s*\d[\d,]*(?:\.\d+)?\s*(?:元|万元|万|美元|USD)?|\d[\d,]*(?:\.\d+)?\s*(?:元|万元|万|美元|USD)"), 0.86),
    ("DATE", "cn-date", re.compile(r"\b(?:19|20)\d{2}[年/-](?:0?[1-9]|1[0-2])(?:[月/-](?:0?[1-9]|[12]\d|3[01])日?)?\b"), 0.75),
    ("ADDRESS", "cn-address", re.compile(r"[\u4e00-\u9fa5]{2,}(?:省|市|区|县|镇|街道|路|号楼|园区|大厦|基地)"), 0.7),
)

COMMON_PERSONS = ("张三", "李四", "王五", "赵六", "陈七", "刘强", "王芳", "李娜", "张伟")
PERSON_CONTEXT = re.compile(r"(?:姓名|联系人|负责人|员工|代表|由|甲方代表|乙方代表)[:：\s]*([\u4e00-\u9fa5]{2,4})")
ORG_CONTEXT = re.compile(r"(?:在|代表|来自|客户|供应商|公司|主体)[:：\s]*([\u4e00-\u9fa5A-Za-z0-9（）()]{2,32}(?:科技|公司|集团|大学|医院|实验室|中心|研究院|有限公司))")


class RedactionDetector:
    def __init__(self, policy: Policy, base_dir: Optional[Path] = None):
        self.policy = policy
        self.base_dir = Path(base_dir or Path.cwd())
        self.dictionary_terms = self._load_dictionaries()
        self._presidio_available = importlib.util.find_spec("presidio_analyzer") is not None

    def detect(self, text: str, source_id: str = "inline") -> List[Finding]:
        findings: List[Finding] = []
        for entity_type, detector, pattern, confidence in SECRET_PATTERNS:
            findings.extend(self._regex_findings(text, source_id, entity_type, detector, pattern, confidence, "critical"))
        for entity_type, detector, pattern, confidence in PII_PATTERNS:
            findings.extend(self._regex_findings(text, source_id, entity_type, detector, pattern, confidence, "medium"))
        findings.extend(self._dictionary_findings(text, source_id))
        findings.extend(self._heuristic_name_findings(text, source_id))
        return adjudicate_findings(findings)

    def _regex_findings(
        self,
        text: str,
        source_id: str,
        entity_type: str,
        detector: str,
        pattern: re.Pattern,
        confidence: float,
        risk: str,
    ) -> List[Finding]:
        action = self.policy.action_for(entity_type)
        return [
            Finding(
                entity_type=entity_type,
                action=action,
                source_id=source_id,
                start=match.start(),
                end=match.end(),
                confidence=confidence,
                detector=detector,
                risk=risk if action == "fail" else risk,
                locator={"kind": "text", "start": match.start(), "end": match.end()},
                value=match.group(0),
            )
            for match in pattern.finditer(text)
        ]

    def _dictionary_findings(self, text: str, source_id: str) -> List[Finding]:
        findings: List[Finding] = []
        for term, entity_type in self.dictionary_terms:
            if not term:
                continue
            start = text.find(term)
            while start >= 0:
                end = start + len(term)
                findings.append(
                    Finding(
                        entity_type=entity_type,
                        action=self.policy.action_for(entity_type),
                        source_id=source_id,
                        start=start,
                        end=end,
                        confidence=0.98,
                        detector="dictionary",
                        risk="medium",
                        locator={"kind": "text", "start": start, "end": end},
                        value=term,
                    )
                )
                start = text.find(term, end)
        return findings

    def _heuristic_name_findings(self, text: str, source_id: str) -> List[Finding]:
        findings: List[Finding] = []
        for name in COMMON_PERSONS:
            start = text.find(name)
            while start >= 0:
                findings.append(self._span_finding("PERSON", "cn-person-common", source_id, start, start + len(name), 0.88, text[start : start + len(name)]))
                start = text.find(name, start + len(name))
        for pattern, entity_type, detector_name, group_index in (
            (PERSON_CONTEXT, "PERSON", "cn-person-context", 1),
            (ORG_CONTEXT, "ORG", "cn-org-context", 1),
        ):
            for match in pattern.finditer(text):
                start, end = match.span(group_index)
                findings.append(self._span_finding(entity_type, detector_name, source_id, start, end, 0.84, match.group(group_index)))
        return findings

    def _span_finding(self, entity_type: str, detector: str, source_id: str, start: int, end: int, confidence: float, value: str) -> Finding:
        return Finding(
            entity_type=entity_type,
            action=self.policy.action_for(entity_type),
            source_id=source_id,
            start=start,
            end=end,
            confidence=confidence,
            detector=detector,
            risk="medium",
            locator={"kind": "text", "start": start, "end": end},
            value=value,
        )

    def _load_dictionaries(self) -> List[Tuple[str, str]]:
        loaded: List[Tuple[str, str]] = []
        for spec in self.policy.dictionaries:
            path = Path(spec.source)
            if not path.is_absolute():
                candidates = [self.base_dir / path, Path(__file__).resolve().parents[2] / path]
                path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                for row in reader:
                    if not row:
                        continue
                    term = row[0].strip()
                    if term and term.lower() not in {"name", "term", "value"}:
                        loaded.append((term, spec.entity))
        return loaded


def adjudicate_findings(findings: Iterable[Finding]) -> List[Finding]:
    accepted: List[Finding] = []
    sorted_findings = sorted(
        findings,
        key=lambda item: (
            1 if item.action == "fail" else 0,
            item.confidence,
            item.length,
            _entity_priority(item.entity_type),
        ),
        reverse=True,
    )
    for finding in sorted_findings:
        if finding.length <= 0:
            continue
        if any(finding.overlaps(existing) for existing in accepted):
            continue
        accepted.append(finding)
    return sorted(accepted, key=lambda item: (item.source_id, item.start, item.end))


def _action_priority(action: str) -> int:
    return {"fail": 100, "tokenize": 70, "redact": 60, "mask": 55, "generalize": 50, "bucket": 45, "month_only": 40}.get(action, 10)


def _entity_priority(entity_type: str) -> int:
    return {"PRIVATE_KEY": 100, "API_KEY": 95, "JWT": 90, "PASSWORD": 85, "COOKIE": 80}.get(entity_type, 20)
