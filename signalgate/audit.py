from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .models import InterruptRecord


def append_interrupt(audit_dir: Path, rec: InterruptRecord) -> Path:
    """
    审计写入：只记录事实（默认不输出）。
    """
    p = audit_dir / "interrupts.jsonl"
    line = json.dumps(rec.__dict__, ensure_ascii=False)
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return p


def summarize_interrupts(audit_dir: Path) -> str:
    """
    用户显式调用 audit 时才输出摘要（最小）。
    """
    p = audit_dir / "interrupts.jsonl"
    if not p.exists():
        return "No interrupts."

    cnt = 0
    with p.open("r", encoding="utf-8") as f:
        for _ in f:
            cnt += 1
    return f"Interrupt count: {cnt}"
