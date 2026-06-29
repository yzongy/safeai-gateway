from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml


DEFAULT_POLICY = {
    "mode": "ai_collaboration",
    "default_action": "replace",
    "fail_on": ["SECRET", "API_KEY", "PASSWORD", "PRIVATE_KEY", "JWT", "COOKIE"],
    "entities": {
        "SECRET": "fail",
        "API_KEY": "fail",
        "PASSWORD": "fail",
        "PRIVATE_KEY": "fail",
        "JWT": "fail",
        "COOKIE": "fail",
        "PERSON": "tokenize",
        "ORG": "tokenize",
        "PROJECT": "tokenize",
        "CUSTOMER": "tokenize",
        "SUPPLIER": "tokenize",
        "SAMPLE_ID": "tokenize",
        "PHONE": "redact",
        "EMAIL": "mask",
        "ID_CARD": "redact",
        "BANK_CARD": "redact",
        "ADDRESS": "generalize",
        "DATE": "month_only",
        "MONEY": "bucket",
        "CONTRACT_ID": "tokenize",
        "USCC": "tokenize",
    },
    "custom_terms": [
        {"source": "examples/dictionaries/employees.csv", "entity": "PERSON"},
        {"source": "examples/dictionaries/customers.csv", "entity": "ORG"},
        {"source": "examples/dictionaries/projects.csv", "entity": "PROJECT"},
    ],
}


@dataclass(frozen=True)
class DictionarySpec:
    source: str
    entity: str


@dataclass(frozen=True)
class Policy:
    name: str
    default_action: str
    entities: Dict[str, str]
    fail_on: List[str] = field(default_factory=list)
    dictionaries: List[DictionarySpec] = field(default_factory=list)
    source_path: Optional[Path] = None

    def action_for(self, entity_type: str) -> str:
        if entity_type in self.fail_on:
            return "fail"
        return self.entities.get(entity_type, self.default_action)

    def is_fail_entity(self, entity_type: str) -> bool:
        return self.action_for(entity_type) == "fail"


def load_policy(policy: str = "strict-ai") -> Policy:
    if policy in ("strict-ai", "strict_ai", "default"):
        data = DEFAULT_POLICY
        source_path = None
        name = "strict-ai"
    else:
        source_path = Path(policy).expanduser().resolve()
        with source_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        name = source_path.stem

    dictionaries = [
        DictionarySpec(source=str(item.get("source", "")), entity=str(item.get("entity", "CUSTOM")))
        for item in data.get("custom_terms", [])
        if item.get("source")
    ]
    return Policy(
        name=name,
        default_action=str(data.get("default_action", "replace")),
        entities={str(k): str(v) for k, v in (data.get("entities") or {}).items()},
        fail_on=[str(item) for item in data.get("fail_on", [])],
        dictionaries=dictionaries,
        source_path=source_path,
    )


def policy_entity_types(policy: Policy) -> Iterable[str]:
    return sorted(set(policy.entities) | set(policy.fail_on))
