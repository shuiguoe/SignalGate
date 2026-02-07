from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

import yaml


@dataclass
class GateState:
    tripped: bool = False
    burst_count: int = 0
    burst_window_start: str = ""  # ISO
    last_interrupt_ts: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_rules(config_dir: Path) -> Dict:
    p = config_dir / "rules.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def load_state(state_dir: Path) -> GateState:
    p = state_dir / "gate.json"
    if not p.exists():
        return GateState()
    obj = json.loads(p.read_text(encoding="utf-8"))
    return GateState(
        tripped=bool(obj.get("tripped", False)),
        burst_count=int(obj.get("burst_count", 0)),
        burst_window_start=str(obj.get("burst_window_start", "")),
        last_interrupt_ts=str(obj.get("last_interrupt_ts", "")),
    )


def save_state(state_dir: Path, st: GateState) -> None:
    p = state_dir / "gate.json"
    p.write_text(json.dumps(st.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")


def can_interrupt(config_dir: Path, state_dir: Path) -> bool:
    st = load_state(state_dir)
    return not st.tripped


def on_interrupt(config_dir: Path, state_dir: Path) -> GateState:
    """
    熔断机制（硬约束）：
    - 1 小时内 >=2 次 interrupt => tripped = True
    """
    rules = load_rules(config_dir).get("gate", {})
    window_min = int(rules.get("burst_window_minutes", 60))
    limit = int(rules.get("burst_limit", 2))

    now = _utc_now()
    st = load_state(state_dir)

    if st.burst_window_start:
        start = datetime.fromisoformat(st.burst_window_start)
    else:
        start = now

    if now - start > timedelta(minutes=window_min):
        # reset window
        st.burst_window_start = now.isoformat()
        st.burst_count = 1
    else:
        # same window
        if not st.burst_window_start:
            st.burst_window_start = start.isoformat()
        st.burst_count += 1

    st.last_interrupt_ts = now.isoformat()

    if st.burst_count >= limit:
        st.tripped = True

    save_state(state_dir, st)
    return st


def reset_gate(state_dir: Path) -> None:
    save_state(state_dir, GateState())
