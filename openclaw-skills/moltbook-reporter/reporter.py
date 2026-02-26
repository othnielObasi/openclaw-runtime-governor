"""
reporter.py – OpenClaw Governor × Moltbook Reporter Skill
==========================================================
This skill does three things:

1. FETCH  – Pull live governance stats from the Governor service
2. COMPOSE – Generate a rich, contextual Moltbook post based on those stats
3. POST   – Publish to the Moltbook `lablab` submolt (or any configured submolt)

It can be called as:
  a) A one-shot function from another OpenClaw skill
  b) An autonomous background loop (run_loop) that posts on a schedule
  c) A standalone CLI script: `python reporter.py`

Environment variables
---------------------
  GOVERNOR_URL          Base URL of the governor service     [http://localhost:8000]
  MOLTBOOK_API_KEY      Moltbook Bearer token (required to post)
  MOLTBOOK_API_URL      Moltbook API base URL                [https://www.moltbook.com/api/v1]
  MOLTBOOK_SUBMOLT      Target submolt                       [lablab]
  MOLTBOOK_AGENT_NAME   Agent display name in posts          [OpenClaw Governor]
  REPORTER_INTERVAL_SEC Seconds between autonomous posts     [7200 = 2 hours]
  REPORTER_DRY_RUN      If "true", compose but do not post   [false]
"""
from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

import httpx
import json

from moltbook_client import MoltbookClient, PostResult
from post_composer import GovernorSnapshot, PostType, compose_post

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("moltbook-reporter")

GOVERNOR_URL = os.getenv("GOVERNOR_URL", "http://localhost:8000")
MOLTBOOK_API_KEY = os.getenv("MOLTBOOK_API_KEY", "")
MOLTBOOK_SUBMOLT = os.getenv("MOLTBOOK_SUBMOLT", "lablab")
MOLTBOOK_AGENT_NAME = os.getenv("MOLTBOOK_AGENT_NAME", "OpenClaw Governor")
REPORTER_INTERVAL_SEC = int(os.getenv("REPORTER_INTERVAL_SEC", "7200"))
REPORTER_DRY_RUN = os.getenv("REPORTER_DRY_RUN", "false").lower() == "true"

_GOVERNOR_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Governor data fetching
# ---------------------------------------------------------------------------

@dataclass
class GovernorData:
    total_actions: int
    blocked: int
    allowed: int
    under_review: int
    avg_risk: float
    kill_switch_active: bool
    top_blocked_tool: Optional[str]
    recent_high_risk_count: int


def _fetch_summary() -> dict:
    with httpx.Client(timeout=_GOVERNOR_TIMEOUT) as client:
        resp = client.get(f"{GOVERNOR_URL}/summary/moltbook")
        resp.raise_for_status()
    return resp.json()


def _fetch_admin_status() -> dict:
    try:
        with httpx.Client(timeout=_GOVERNOR_TIMEOUT) as client:
            resp = client.get(f"{GOVERNOR_URL}/admin/status")
            resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Could not fetch admin status: %s", exc)
        return {"kill_switch": False}


def _fetch_recent_high_risk(threshold: int = 80, limit: int = 200) -> int:
    try:
        with httpx.Client(timeout=_GOVERNOR_TIMEOUT) as client:
            resp = client.get(
                f"{GOVERNOR_URL}/actions",
                params={"limit": limit, "decision": "block"},
            )
            resp.raise_for_status()
        actions = resp.json()
        return sum(1 for a in actions if a.get("risk_score", 0) >= threshold)
    except Exception as exc:
        logger.warning("Could not fetch recent high-risk count: %s", exc)
        return 0


def _fetch_top_blocked_tool(limit: int = 200) -> Optional[str]:
    try:
        with httpx.Client(timeout=_GOVERNOR_TIMEOUT) as client:
            resp = client.get(
                f"{GOVERNOR_URL}/actions",
                params={"limit": limit, "decision": "block"},
            )
            resp.raise_for_status()
        actions = resp.json()
        counts: dict[str, int] = {}
        for a in actions:
            tool = a.get("tool", "unknown")
            counts[tool] = counts.get(tool, 0) + 1
        return max(counts, key=counts.get) if counts else None
    except Exception as exc:
        logger.warning("Could not fetch top blocked tool: %s", exc)
        return None


def fetch_governor_data() -> GovernorData:
    """Aggregate all governor data needed to compose a Moltbook post."""
    summary = _fetch_summary()
    admin = _fetch_admin_status()
    high_risk_count = _fetch_recent_high_risk()
    top_tool = _fetch_top_blocked_tool()

    return GovernorData(
        total_actions=summary.get("total_actions", 0),
        blocked=summary.get("blocked", 0),
        allowed=summary.get("allowed", 0),
        under_review=summary.get("under_review", 0),
        avg_risk=float(summary.get("avg_risk", 0.0)),
        kill_switch_active=admin.get("kill_switch", False),
        top_blocked_tool=top_tool,
        recent_high_risk_count=high_risk_count,
    )


# ---------------------------------------------------------------------------
# State tracking
# ---------------------------------------------------------------------------

_last_total_actions: int = 0


def _to_snapshot(data: GovernorData, session_actions: int = 0) -> GovernorSnapshot:
    return GovernorSnapshot(
        total_actions=data.total_actions,
        blocked=data.blocked,
        allowed=data.allowed,
        under_review=data.under_review,
        avg_risk=data.avg_risk,
        kill_switch_active=data.kill_switch_active,
        top_blocked_tool=data.top_blocked_tool,
        recent_high_risk_count=data.recent_high_risk_count,
        session_actions=session_actions,
    )


# ---------------------------------------------------------------------------
# Core public functions
# ---------------------------------------------------------------------------

def fetch_summary() -> GovernorData:
    """Public alias – fetch current governor stats."""
    return fetch_governor_data()


def build_status_text() -> str:
    """One-line status string. Does NOT post to Moltbook."""
    data = fetch_governor_data()
    block_pct = round(data.blocked / data.total_actions * 100) if data.total_actions else 0
    return (
        f"[{MOLTBOOK_AGENT_NAME}] {data.total_actions} actions evaluated | "
        f"{data.blocked} blocked ({block_pct}%) | "
        f"avg risk {data.avg_risk:.1f}/100 | "
        f"kill_switch={'ON' if data.kill_switch_active else 'off'}"
    )


def post_update(
    force_type: Optional[PostType] = None,
    session_actions: int = 0,
) -> Optional[PostResult]:
    """
    Fetch governor data, compose a post, and publish it to Moltbook.

    Returns PostResult if posted successfully, None if dry-run or no API key.
    """
    logger.info("Collecting governor data...")
    try:
        data = fetch_governor_data()
    except Exception as exc:
        logger.error("Failed to fetch governor data: %s", exc)
        return None

    snap = _to_snapshot(data, session_actions=session_actions)
    composed = compose_post(snap, force_type=force_type)

    logger.info("Composed post [%s]: %r", composed.post_type.value, composed.title)

    if REPORTER_DRY_RUN:
        logger.info(
            "DRY RUN — would post to submolt=%r\nTitle: %s\n\n%s",
            MOLTBOOK_SUBMOLT, composed.title, composed.content,
        )
        return None

    if not MOLTBOOK_API_KEY:
        logger.warning(
            "MOLTBOOK_API_KEY not set — skipping post. "
            "Set it to enable autonomous posting."
        )
        return None

    client = MoltbookClient(api_key=MOLTBOOK_API_KEY)
    try:
        result = client.post(
            submolt=MOLTBOOK_SUBMOLT,
            title=composed.title,
            content=composed.content,
            tags=composed.tags,
        )
        # Handle verification challenge if present
        try:
            raw = result.raw if hasattr(result, "raw") else {}
            post_obj = raw.get("post", raw) if isinstance(raw, dict) else {}
            verification = post_obj.get("verification") or raw.get("verification")
        except Exception:
            verification = None

        if verification:
            cfg_dir = os.path.expanduser("~/.config/moltbook")
            os.makedirs(cfg_dir, exist_ok=True)
            pending = {
                "verification_code": verification.get("verification_code"),
                "challenge_text": verification.get("challenge_text"),
                "expires_at": verification.get("expires_at"),
                "post_id": post_obj.get("id"),
            }
            pending_path = os.path.join(cfg_dir, "pending_verification.json")
            with open(pending_path, "w") as f:
                json.dump(pending, f)

            logger.warning(
                "Moltbook returned a verification challenge. Saved to %s. "
                "Solve the challenge and run openclaw-skills/moltbook-reporter/verify_challenge.py to submit the answer.",
                pending_path,
            )
        logger.info(
            "✅ Posted to Moltbook submolt=%r post_id=%s",
            MOLTBOOK_SUBMOLT, result.post_id,
        )
        return result
    except Exception as exc:
        logger.error("Failed to post to Moltbook: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Autonomous posting loop
# ---------------------------------------------------------------------------

def run_loop(interval_sec: int = REPORTER_INTERVAL_SEC) -> None:
    """
    Autonomous posting loop. Runs indefinitely, posting to Moltbook on a
    configurable schedule. Handles all errors gracefully.

    Minimum enforced interval: 1800s (30 min) — Moltbook rate limit.
    Recommended interval:      7200s (2 hours) — comfortable headroom.

    Moltbook rate limits (from official docs):
      - Posts:    1 / 30 minutes
      - Comments: 50 / hour
      - General:  100 / minute
    """
    global _last_total_actions

    safe_interval = max(interval_sec, 1800)
    if safe_interval != interval_sec:
        logger.warning(
            "REPORTER_INTERVAL_SEC=%d is below the 30-minute Moltbook post rate limit. "
            "Clamped to %d seconds.",
            interval_sec, safe_interval,
        )

    logger.info(
        "🚀 Moltbook reporter autonomous loop starting. "
        "submolt=%r  interval=%ds  dry_run=%s",
        MOLTBOOK_SUBMOLT, safe_interval, REPORTER_DRY_RUN,
    )

    # Post immediately on startup
    logger.info("Posting initial startup heartbeat...")
    post_update(force_type=PostType.HEARTBEAT)

    try:
        initial_data = fetch_governor_data()
        _last_total_actions = initial_data.total_actions
    except Exception:
        _last_total_actions = 0

    while True:
        logger.info("Sleeping %ds until next Moltbook post...", safe_interval)
        time.sleep(safe_interval)

        try:
            data = fetch_governor_data()
            session_delta = max(0, data.total_actions - _last_total_actions)
            _last_total_actions = data.total_actions

            result = post_update(session_actions=session_delta)

            if result:
                logger.info(
                    "Autonomous post complete (session delta: +%d actions). "
                    "Next in %ds.",
                    session_delta, safe_interval,
                )

        except KeyboardInterrupt:
            logger.info("Moltbook reporter loop stopped by KeyboardInterrupt.")
            break
        except Exception as exc:
            logger.error(
                "Unexpected error in reporter loop (will continue): %s",
                exc, exc_info=True,
            )


# ---------------------------------------------------------------------------
# OpenClaw skill handler
# ---------------------------------------------------------------------------

def handle(args: dict, context: dict) -> dict:
    """
    OpenClaw skill entry point. Called by the OpenClaw runtime.

    args["action"] options:
      "post"       – Post one update now (default)
      "status"     – Return status text without posting
      "start_loop" – Start the autonomous loop (blocking)

    args["post_type"] (optional):
      One of: heartbeat | milestone | insight | incident | reflection
    """
    action = args.get("action", "post")
    force_type_str = args.get("post_type")
    force_type = PostType(force_type_str) if force_type_str else None

    if action == "status":
        return {"status": "ok", "message": build_status_text()}

    if action == "start_loop":
        interval = int(args.get("interval_sec", REPORTER_INTERVAL_SEC))
        run_loop(interval_sec=interval)
        return {"status": "ok", "message": "Loop ended."}

    result = post_update(force_type=force_type)
    if result:
        return {
            "status": "posted",
            "message": f"Posted to Moltbook submolt='{MOLTBOOK_SUBMOLT}'",
            "post_id": result.post_id,
        }
    return {
        "status": "skipped",
        "message": "Post skipped (dry run or missing API key). " + build_status_text(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="OpenClaw Governor × Moltbook Reporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reporter.py --action post
  python reporter.py --action post --post-type insight
  python reporter.py --action status
  python reporter.py --action loop --interval 3600
  python reporter.py --action post --dry-run
        """,
    )
    parser.add_argument(
        "--action",
        choices=["post", "status", "loop"],
        default="post",
        help="post: publish one update | status: print status | loop: run autonomous loop",
    )
    parser.add_argument(
        "--post-type",
        choices=[t.value for t in PostType],
        default=None,
        help="Force a specific post type",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=REPORTER_INTERVAL_SEC,
        help=f"Loop interval in seconds (default: {REPORTER_INTERVAL_SEC})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compose post content but do not publish to Moltbook",
    )
    cli_args = parser.parse_args()

    if cli_args.dry_run:
        os.environ["REPORTER_DRY_RUN"] = "true"
        # reload module-level constant
        import importlib, sys as _sys
        REPORTER_DRY_RUN = True

    force = PostType(cli_args.post_type) if cli_args.post_type else None

    if cli_args.action == "status":
        print(build_status_text())
        sys.exit(0)

    if cli_args.action == "loop":
        run_loop(interval_sec=cli_args.interval)
        sys.exit(0)

    result = post_update(force_type=force)
    if result:
        print(f"✅ Posted: {result.title}")
        print(f"   Post ID : {result.post_id}")
        print(f"   Submolt : {MOLTBOOK_SUBMOLT}")
    else:
        print(build_status_text())
