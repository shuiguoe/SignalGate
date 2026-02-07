from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


ENV_HOME = "SIGNALGATE_HOME"


@dataclass(frozen=True)
class Paths:
    root: Path
    config_dir: Path
    data_dir: Path
    cold_dir: Path
    audit_dir: Path
    state_dir: Path


def resolve_root(cli_root: Optional[str]) -> Path:
    """
    路径解析优先级（硬约束）：
      1) CLI 参数 --root
      2) 环境变量 SIGNALGATE_HOME
      3) 当前工作目录
    """
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    env = os.environ.get(ENV_HOME, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def get_paths(cli_root: Optional[str]) -> Paths:
    root = resolve_root(cli_root)
    config_dir = root / "config"
    data_dir = root / "data"
    cold_dir = data_dir / "cold"
    audit_dir = data_dir / "audit"
    state_dir = data_dir / "state"

    for d in (config_dir, cold_dir, audit_dir, state_dir):
        d.mkdir(parents=True, exist_ok=True)

    return Paths(
        root=root,
        config_dir=config_dir,
        data_dir=data_dir,
        cold_dir=cold_dir,
        audit_dir=audit_dir,
        state_dir=state_dir,
    )
