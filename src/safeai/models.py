from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Finding:
    entity_type: str
    action: str
    source_id: str
    start: int
    end: int
    confidence: float
    detector: str
    risk: str = "medium"
    locator: Dict[str, object] = field(default_factory=dict)
    value: str = field(default="", repr=False, compare=False)

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)

    def overlaps(self, other: "Finding") -> bool:
        return self.source_id == other.source_id and self.start < other.end and other.start < self.end

    def to_report_dict(self) -> Dict[str, object]:
        return {
            "entity_type": self.entity_type,
            "action": self.action,
            "source_id": self.source_id,
            "start": self.start,
            "end": self.end,
            "confidence": round(self.confidence, 3),
            "detector": self.detector,
            "risk": self.risk,
            "locator": self.locator or {"kind": "text", "start": self.start, "end": self.end},
        }


@dataclass(frozen=True)
class ExtractedDocument:
    path: Path
    source_id: str
    text: str
    status: str
    media_type: str
    sha256: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class FileResult:
    source_id: str
    path: Path
    status: str
    output_path: Optional[Path]
    finding_count: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    blocked: bool
    report_path: Path
    bundle_path: Path
    output_dir: Path
    findings: List[Finding]
    files: List[FileResult]


@dataclass(frozen=True)
class RestoreResult:
    run_id: str
    input_path: Path
    output_path: Path
    restored_tokens: int
