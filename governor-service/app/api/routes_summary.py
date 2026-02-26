from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, desc

from ..auth.dependencies import require_any
from ..database import db_session
from ..models import ActionLog, User
from ..schemas import SummaryOut

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/moltbook", response_model=SummaryOut)
def moltbook_summary(_user: User = Depends(require_any)) -> SummaryOut:
    """
    Rich governance summary for Moltbook reporter consumption.

    Returns per-decision counts, average risk score, top blocked tool,
    and a pre-formatted narrative message — all the data the reporter
    skill needs in a single call.
    """
    with db_session() as session:
        total = session.execute(select(func.count(ActionLog.id))).scalar_one() or 0

        blocked = (
            session.execute(
                select(func.count(ActionLog.id)).where(ActionLog.decision == "block")
            ).scalar_one() or 0
        )
        allowed = (
            session.execute(
                select(func.count(ActionLog.id)).where(ActionLog.decision == "allow")
            ).scalar_one() or 0
        )
        under_review = (
            session.execute(
                select(func.count(ActionLog.id)).where(ActionLog.decision == "review")
            ).scalar_one() or 0
        )
        avg_risk = (
            session.execute(select(func.avg(ActionLog.risk_score))).scalar_one() or 0.0
        )

        # Top blocked tool – most frequently occurring tool in blocked actions
        top_blocked_row = (
            session.execute(
                select(ActionLog.tool, func.count(ActionLog.id).label("cnt"))
                .where(ActionLog.decision == "block")
                .group_by(ActionLog.tool)
                .order_by(desc("cnt"))
                .limit(1)
            ).first()
        )
        top_blocked_tool = top_blocked_row[0] if top_blocked_row else None

        # High-risk count (risk_score >= 80)
        high_risk = (
            session.execute(
                select(func.count(ActionLog.id)).where(ActionLog.risk_score >= 80)
            ).scalar_one() or 0
        )

    block_pct = round(blocked / total * 100) if total else 0

    if total == 0:
        message = "No governed actions have been processed yet."
    else:
        message = (
            f"Governor update: evaluated {total} actions in total. "
            f"Allowed {allowed}, blocked {blocked} ({block_pct}%), "
            f"sent {under_review} for review. "
            f"Average risk score: {float(avg_risk):.1f}/100. "
            f"High-risk actions (≥80): {high_risk}."
        )
        if top_blocked_tool:
            message += f" Most blocked tool: {top_blocked_tool}."

    return SummaryOut(
        total_actions=total,
        blocked=blocked,
        allowed=allowed,
        under_review=under_review,
        avg_risk=float(avg_risk),
        top_blocked_tool=top_blocked_tool,
        high_risk_count=high_risk,
        message=message,
    )
