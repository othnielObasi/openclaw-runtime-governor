from __future__ import annotations

import json

from ..database import db_session
from ..models import ActionLog
from ..schemas import ActionDecision, ActionInput


def log_action(action: ActionInput, decision: ActionDecision) -> None:
    """
    Persist a governed action to the audit log.

    Context metadata (agent_id, session_id, user_id, channel, trace_id,
    span_id) is extracted from action.context and stored as indexed
    columns for easy filtering and trace correlation.
    """
    ctx = action.context or {}

    with db_session() as session:
        row = ActionLog(
            tool=action.tool,
            args=json.dumps(action.args),
            context=json.dumps(ctx),
            # Context metadata
            agent_id=ctx.get("agent_id"),
            session_id=ctx.get("session_id"),
            user_id=ctx.get("user_id"),
            channel=ctx.get("channel"),
            # Trace correlation
            trace_id=ctx.get("trace_id"),
            span_id=ctx.get("span_id"),
            # Decision
            decision=decision.decision,
            risk_score=decision.risk_score,
            explanation=decision.explanation,
            policy_ids=",".join(decision.policy_ids),
        )
        session.add(row)
