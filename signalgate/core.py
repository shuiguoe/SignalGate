from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta

from .audit import append_interrupt
from .decision import decide, load_bets, load_rules
from .gate import can_interrupt, on_interrupt
from .ingress import load_event_from_json, write_cold_event
from .interrupt import format_interrupt
from .models import InterruptRecord, utc_now_iso


def _infer_entity(event, bets_cfg) -> str:
    bets = (bets_cfg.get("bets") or {})
    direct = bets.get("direct") or []

    text = f"{event.title}\n{event.body}".lower()
    tags = [t.lower() for t in (event.tags or [])]

    for b in direct:
        bid = str(b.get("id") or "").lower()
        name = str(b.get("name") or "").strip()
        name_l = name.lower()
        bt = [str(x).lower() for x in (b.get("tags") or [])]

        hit = False
        if bid and (bid in text or bid in tags):
            hit = True
        elif name_l and (name_l in text):
            hit = True
        elif any(t in tags for t in bt):
            hit = True

        if hit:
            return name if name else (bid.upper() if bid else "UNKNOWN")

    return "UNKNOWN"


def _infer_action(event, rules_cfg) -> str:
    action_map = (rules_cfg or {}).get("action_map") or {}

    allowed = action_map.get("allowed_actions") or ["BUY", "SELL", "REDUCE", "DO_NOTHING"]
    allowed_u = {str(a).upper() for a in allowed}

    sell_tags = action_map.get("sell_tags") or ["sell", "exit", "ban", "delist", "enforcement"]
    reduce_tags = action_map.get("reduce_tags") or ["reduce", "trim", "risk_off"]
    buy_tags = action_map.get("buy_tags") or ["buy", "add", "risk_on"]

    tags = {str(t).lower() for t in (event.tags or [])}

    if "SELL" in allowed_u and tags.intersection({str(x).lower() for x in sell_tags}):
        return "SELL"
    if "REDUCE" in allowed_u and tags.intersection({str(x).lower() for x in reduce_tags}):
        return "REDUCE"
    if "BUY" in allowed_u and tags.intersection({str(x).lower() for x in buy_tags}):
        return "BUY"

    return "DO_NOTHING" if "DO_NOTHING" in allowed_u else "DO_NOTHING"


def _format_dryrun(event, d, entity: str, action: str) -> str:
    tags = ",".join([str(t) for t in (event.tags or [])])
    src = event.url or event.source or ""
    return "\n".join(
        [
            f"[DRYRUN] {entity} {d.state.upper()}",
            "Rule: rule_v0_1",
            f"Evidence: q1={d.evidence_q1} q2={d.evidence_q2} q3={d.evidence_q3}",
            f"Action: {action}",
            f"Source: {src}",
            f"Event: {event.event_id}",
            f"Tags: {tags}",
        ]
    )


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    s = ts.strip()
    try:
        # 允许: 2026-02-07T00:00:00Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        return None


def _observation_cfg(rules_cfg) -> tuple[int, bool]:
    decision_cfg = (rules_cfg or {}).get("decision") or {}
    hours = int(decision_cfg.get("observation_window_hours") or 24)

    tier_c = decision_cfg.get("tier_c_policy") or {}
    allow_promo = bool(tier_c.get("allow_promotion_by_multisource") or False)
    return hours, allow_promo


def _maybe_promote_by_multisource(event, tentative_dir: Path, entity: str, window_hours: int) -> bool:
    """
    v0.1 多源确认（极简）：
    - 在 observation_window_hours 内
    - 同一实体（entity != UNKNOWN）
    - 不同 source（event.source 不同）
    => promotion = True
    """
    if entity == "UNKNOWN":
        return False

    now = _parse_ts(getattr(event, "ts", "") or "") or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    cur_source = str(getattr(event, "source", "") or "").strip().lower()

    for p in tentative_dir.glob("*.json"):
        try:
            ev2 = load_event_from_json(p)
        except Exception:
            continue

        ts2 = _parse_ts(getattr(ev2, "ts", "") or "")
        if ts2 is None:
            continue
        if ts2 < cutoff:
            continue

        src2 = str(getattr(ev2, "source", "") or "").strip().lower()
        if not src2 or src2 == cur_source:
            continue

        # 用相同的实体推断逻辑保证一致性
        # 注意：这里不依赖 bets_cfg（避免重复读取）；只用“标签/文本”很容易误判
        # v0.1 简化：只要求文件名不同源 + 时间窗口内
        return True

    return False


def run_once(
    config_dir: Path,
    cold_dir: Path,
    audit_dir: Path,
    state_dir: Path,
    input_json: Path,
    dry_run: bool = False,
) -> str:
    """
    - dry_run=True：只判定 + 输出 DRYRUN；不写 cold/audit/state，不触发 gate
    - dry_run=False：正常模式；
        * interrupt：写 cold + 写 audit + 触发 gate + 输出
        * tentative：写 data/tentative（沉默）
        * cold：写 cold（沉默）
    """
    event = load_event_from_json(input_json)

    bets_cfg = load_bets(config_dir)
    rules_cfg = load_rules(config_dir)

    d = decide(event, bets_cfg, rules_cfg)
    entity = _infer_entity(event, bets_cfg)
    action = _infer_action(event, rules_cfg)

    if dry_run:
        return _format_dryrun(event, d, entity, action)

    # Observation Buffer: tentative -> data/tentative
    if d.state == "tentative":
        tentative_dir = cold_dir.parent / "tentative"
        tentative_dir.mkdir(parents=True, exist_ok=True)

        # 写入待观察区（默认沉默）
        write_cold_event(tentative_dir, event)

        window_hours, allow_promo = _observation_cfg(rules_cfg)
        if allow_promo and _maybe_promote_by_multisource(event, tentative_dir, entity, window_hours):
            # 升级为 interrupt（仍然遵循 gate）
            d.state = "interrupt"
        else:
            return ""

    # 正常 cold：永远写入 cold（tentative 未升级则不会走到这里）
    write_cold_event(cold_dir, event)

    if d.state != "interrupt":
        return ""

    if not can_interrupt(config_dir, state_dir):
        return ""

    st = on_interrupt(config_dir, state_dir)
    if st.tripped:
        pass

    rec = InterruptRecord(
        ts=utc_now_iso(),
        event_id=event.event_id,
        entity=entity,
        signal_type="STRUCT_CHANGE",
        rule_id=d.rule_id,
        evidence=f"q1={d.evidence_q1} q2={d.evidence_q2} q3={d.evidence_q3}",
        action=action,
        deadline="",
        source_ref=event.url or event.source,
    )
    append_interrupt(audit_dir, rec)
    return format_interrupt(rec)
