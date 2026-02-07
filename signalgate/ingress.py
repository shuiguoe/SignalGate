from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import Event, utc_now_iso


def load_event_from_json(path: Path) -> Event:
    """
    v0.1：最小 ingress
    - 读取一个 JSON 文件作为事件输入（你可以手动丢文件/或后续接 RSS/API）
    """
    obj = json.loads(path.read_text(encoding="utf-8"))
    return Event(
        event_id=str(obj.get("event_id") or obj.get("id") or path.stem),
        ts=str(obj.get("ts") or utc_now_iso()),
        title=str(obj.get("title") or ""),
        body=str(obj.get("body") or ""),
        url=str(obj.get("url") or ""),
        source=str(obj.get("source") or ""),
        source_tier=str(obj.get("source_tier") or "C"),
        tags=list(obj.get("tags") or []),
    )


def write_cold_event(cold_dir: Path, event: Event) -> Path:
    """
    冷存写入：默认墓地（无输出、无提示）。
    """
    out = cold_dir / f"{event.event_id}.json"
    out.write_text(json.dumps(event.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out
