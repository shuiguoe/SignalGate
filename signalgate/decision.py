from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from .models import Decision, Event


def load_yaml(path: Path) -> Dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_bets(config_dir: Path) -> Dict:
    p = config_dir / "bets.yaml"
    if not p.exists():
        return {}
    return load_yaml(p)


def load_rules(config_dir: Path) -> Dict:
    p = config_dir / "rules.yaml"
    if not p.exists():
        return {}
    return load_yaml(p)


def _rank_map(rules_cfg: Dict) -> Dict[str, int]:
    m = (rules_cfg.get("evidence") or {}).get("rank") or {}
    # 默认兜底（不可逆）：C < B < A
    base = {"C": 0, "B": 1, "A": 2}
    for k, v in m.items():
        base[str(k).upper()] = int(v)
    return base


def _evidence_ge(rules_cfg: Dict, a: str, b: str) -> bool:
    rank = _rank_map(rules_cfg)
    return rank.get(str(a).upper(), 0) >= rank.get(str(b).upper(), 0)


def _get_list(d: Dict, path: List[str], default: List[str]) -> List[str]:
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    if cur is None:
        return default
    return [str(x) for x in cur] if isinstance(cur, list) else default


def _get_bool(d: Dict, path: List[str], default: bool) -> bool:
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return bool(cur)


def _get_str(d: Dict, path: List[str], default: str) -> str:
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return str(cur) if cur is not None else default


def _match_direct_bets(event: Event, bets_cfg: Dict, impact_radius: Dict) -> bool:
    """
    Q2：只在 impact_radius.direct=true 时匹配 direct bets。
    indirect/macro 在 v0.1 由配置冻结为 false。
    """
    if not impact_radius.get("direct", True):
        return False

    bets = (bets_cfg.get("bets") or {})
    direct = bets.get("direct") or []

    text = f"{event.title}\n{event.body}".lower()
    tags = [t.lower() for t in (event.tags or [])]

    for b in direct:
        bid = str(b.get("id") or "").lower()
        name = str(b.get("name") or "").lower()
        bt = [str(x).lower() for x in (b.get("tags") or [])]

        if bid and (bid in text or bid in tags):
            return True
        if name and (name in text):
            return True
        if any(t in tags for t in bt):
            return True

    return False


def decide(event: Event, bets_cfg: Dict, rules_cfg: Dict) -> Decision:
    """
    三问法（严格按 rules.yaml）：

    Q1：结构变化？
      - 由 tags 命中 structural/rule_change/regulation 或 force 标签 判定“可能结构”
      - 证据必须 >= decision.q1_min_evidence
      - 若 tier_c_policy.q1_always_no=true 且 source_tier=C，则 Q1 永远为 NO

    Q2：是否影响已下注？
      - direct bets 匹配（受 impact_radius 控制）
      - force 风险标签命中且 bets.force 非空 => Q2=YES（绕过）

    Q3：是否需要改变下一步行动？
      - 若 q3_policy.require_explicit_tag=true，则必须命中 explicit_tags
      - force_tags 命中则视为需要行动（绕过 explicit tag）

    状态机：
      - 仅当 Q1/Q2/Q3 全 YES => interrupt
      - 否则：如果出现“结构/force 迹象” => tentative；否则 cold
    """
    decision_cfg = rules_cfg.get("decision") or {}

    # ---- 基础输入
    tags = [str(t).lower() for t in (event.tags or [])]
    evidence_q1 = str(event.source_tier or "C").upper()
    if evidence_q1 not in ("A", "B", "C"):
        evidence_q1 = "C"

    # ---- Q1：结构变化（候选）
    structural_tags = {"structural", "rule_change", "regulation"}
    force_tags_default = ["tax", "account", "kyc", "transfer", "identity", "legal", "regulation"]
    force_tags = [t.lower() for t in _get_list(rules_cfg, ["decision", "q3_policy", "force_tags"], force_tags_default)]

    structural_hit = any(t in structural_tags for t in tags)
    force_hit = any(t in tags for t in force_tags)

    q1_candidate = bool(structural_hit or force_hit)

    # Q1 阈值：证据强度
    q1_min = _get_str(rules_cfg, ["decision", "q1_min_evidence"], "B").upper()
    if q1_min not in ("A", "B", "C"):
        q1_min = "B"

    # tier C 策略
    q1_always_no_for_c = _get_bool(rules_cfg, ["decision", "tier_c_policy", "q1_always_no"], True)
    if q1_always_no_for_c and evidence_q1 == "C":
        q1 = False
    else:
        q1 = q1_candidate and _evidence_ge(rules_cfg, evidence_q1, q1_min)

    # ---- Q2：影响已下注
    impact_radius = decision_cfg.get("impact_radius") or {"direct": True, "indirect": False, "macro": False}
    q2_direct = _match_direct_bets(event, bets_cfg, impact_radius)

    # force 风险绕过 Q2（需要 bets.force 非空）
    bets = (bets_cfg.get("bets") or {})
    force_list = bets.get("force") or []
    q2_force = bool(force_hit and len(force_list) > 0)

    q2 = bool(q2_direct or q2_force)

    # 证据标注（v0.1：Q2/Q3 仍是工程级“强/弱”标注，不做复杂推断）
    evidence_q2 = "B" if q2 else "C"

    # ---- Q3：需要行动？
    require_explicit = _get_bool(rules_cfg, ["decision", "q3_policy", "require_explicit_tag"], True)
    explicit_tags = [t.lower() for t in _get_list(rules_cfg, ["decision", "q3_policy", "explicit_tags"], ["action_required"])]

    explicit_hit = any(t in tags for t in explicit_tags)
    if require_explicit:
        q3 = bool(explicit_hit or force_hit)
    else:
        # 如果允许非显式标签，v0.1 仍只认 explicit/force（避免误打断）
        q3 = bool(explicit_hit or force_hit)

    evidence_q3 = "B" if q3 else "C"

    # ---- 状态机
    if q1 and q2 and q3:
        state = "interrupt"
    else:
        maybe = bool(q1_candidate or q2_force)
        state = "tentative" if maybe else "cold"

    return Decision(
        q1_structural=q1,
        q2_affects_bets=q2,
        q3_requires_action=q3,
        evidence_q1=evidence_q1,
        evidence_q2=evidence_q2,
        evidence_q3=evidence_q3,
        state=state,
        rule_id="rule_v0_1",
    )
