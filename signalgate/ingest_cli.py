from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .ingress import load_event_from_json, write_cold_event


def _iter_inputs(p: Path, glob_pattern: str) -> List[Path]:
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted([x for x in p.glob(glob_pattern) if x.is_file()])
    return []


def ingest(input_path: Path, cold_dir: Path, glob_pattern: str = "*.json") -> int:
    """
    Ingress v0.1（收集层）：
    - 只负责把事件写入 Cold Store
    - 不过滤、不判定、不打断
    - 默认沉默：不 print
    """
    files = _iter_inputs(input_path, glob_pattern)
    n = 0
    for f in files:
        # v0.1 只 ingest “事件 JSON”，后续再接 RSS/API/文本
        ev = load_event_from_json(f)
        write_cold_event(cold_dir, ev)
        n += 1
    return n
