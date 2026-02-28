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

    # If the SDK sent prompt inline, encrypt it into the context blob for storage
    stored_ctx = dict(ctx)
    if action.prompt:
        from ..encryption import encrypt_value
        stored_ctx["_prompt_encrypted"] = encrypt_value(action.prompt)

    with db_session() as session:
        row = ActionLog(
            tool=action.tool,
            args=json.dumps(action.args),
            context=json.dumps(stored_ctx),
            # Context metadata
            agent_id=ctx.get("agent_id"),
            session_id=ctx.get("session_id"),
            user_id=ctx.get("user_id"),
            channel=ctx.get("channel"),
            # Trace correlation
            trace_id=ctx.get("trace_id"),
            span_id=ctx.get("span_id"),
            # Conversation correlation
            conversation_id=ctx.get("conversation_id"),
            turn_id=ctx.get("turn_id"),
            # Decision
            decision=decision.decision,
            risk_score=decision.risk_score,
            explanation=decision.explanation,
            policy_ids=",".join(decision.policy_ids),
        )
        session.add(row)
