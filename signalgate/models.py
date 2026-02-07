from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    """Ingress 输出的标准事件结构（最小字段集）。"""
    event_id: str
    ts: str
    title: str
    body: str = ""
    url: str = ""
    source: str = ""
    source_tier: str = "C"  # A/B/C
    tags: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tags"] = self.tags or []
        return d


@dataclass(frozen=True)
class Decision:
    """Decision Core 的三问结果 + 证据强度。"""
    q1_structural: bool
    q2_affects_bets: bool
    q3_requires_action: bool
    evidence_q1: str  # A/B/C
    evidence_q2: str  # A/B/C
    evidence_q3: str  # A/B/C
    state: str        # cold / tentative / interrupt
    rule_id: str = "rule_v0_1"


@dataclass(frozen=True)
class InterruptRecord:
    """每次打断必须可审计：为什么当时必须打断。"""
    ts: str
    event_id: str
    entity: str
    signal_type: str
    rule_id: str
    evidence: str
    action: str  # BUY/SELL/REDUCE/DO_NOTHING
    deadline: str = ""
    source_ref: str = ""
