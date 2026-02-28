"""
routes_stream.py — Server-Sent Events (SSE) for real-time monitoring
=====================================================================
Provides ``GET /actions/stream`` which streams governance events as they
happen. Each time an agent's tool call is evaluated, a JSON event is
pushed to every connected client within milliseconds.

Authentication: requires any valid credential (JWT or API key) — same
as the ``list_actions`` endpoint. Auditor / operator / admin roles are
all permitted.

Protocol: standard Server-Sent Events (``text/event-stream``).  Each
message has ``event: action_evaluated`` and ``data: <json>``.  A
``:heartbeat`` comment is sent every 15 s to keep the connection alive
through proxies and load-balancers.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..auth.dependencies import require_any
from ..event_bus import ActionEvent, action_bus
from ..models import User

router = APIRouter(prefix="/actions", tags=["stream"])

HEARTBEAT_INTERVAL = 15  # seconds


async def _event_generator(
    request: Request,
    queue: asyncio.Queue[ActionEvent],
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted messages from the event bus.

    Sends a heartbeat comment every HEARTBEAT_INTERVAL seconds to
    prevent proxies from closing idle connections.  Exits cleanly
    when the client disconnects.
    """
    try:
        # Initial connection event
        yield "event: connected\ndata: {\"status\":\"streaming\"}\n\n"

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=HEARTBEAT_INTERVAL
                )
                yield f"event: {event.event_type}\ndata: {event.to_json()}\n\n"
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield ": heartbeat\n\n"
    finally:
        action_bus.unsubscribe(queue)


@router.get(
    "/stream",
    response_class=StreamingResponse,
    summary="Real-time action event stream (SSE)",
    description=(
        "Opens a Server-Sent Events connection that streams governance "
        "decisions in real time. Every `POST /actions/evaluate` call "
        "triggers an `action_evaluated` event on this stream."
    ),
    responses={
        200: {
            "description": "SSE stream of action events",
            "content": {"text/event-stream": {}},
        }
    },
)
async def stream_actions(
    request: Request,
    _user: User = Depends(require_any),
):
    """Stream governance events in real time via Server-Sent Events.

    Connect with ``EventSource`` or ``curl -N``:
    ```
    curl -N -H "X-API-Key: ocg_..." https://openclaw-governor.fly.dev/actions/stream
    ```

    Events:
    - ``connected``: sent immediately on connection
    - ``action_evaluated``: sent for each governance decision

    A ``:heartbeat`` comment is sent every ~15 s.
    """
    try:
        queue = action_bus.subscribe()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return StreamingResponse(
        _event_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx: disable response buffering
        },
    )


@router.get(
    "/stream/status",
    summary="Stream connection status",
    description="Returns the number of active SSE subscribers.",
)
async def stream_status(
    _user: User = Depends(require_any),
):
    """Check how many clients are listening to the real-time stream."""
    return {
        "active_subscribers": action_bus.subscriber_count,
        "heartbeat_interval_sec": HEARTBEAT_INTERVAL,
    }
