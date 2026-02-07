from __future__ import annotations

from .models import InterruptRecord


def format_interrupt(rec: InterruptRecord) -> str:
    """
    打断消息模板（冻结）
    - 禁止情绪词/预测词（v0.1 仅靠模板约束，后续可加禁词校验）
    """
    deadline = rec.deadline or "None"
    src = rec.source_ref or "None"
    return (
        f"[INTERRUPT] {rec.entity} {rec.signal_type}\n"
        f"Rule: {rec.rule_id}\n"
        f"Evidence: {rec.evidence}\n"
        f"Action: {rec.action} | Deadline: {deadline}\n"
        f"Source: {src}\n"
    )
