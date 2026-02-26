"""
auto_run.py
Orchestrator script intended to be run from cron. It will:
 - Run the reporter one-shot post (honoring REPORTER_DRY_RUN)
 - Attempt to auto-solve any pending verification challenge

Usage (cron):
 PYTHONPATH=./openclaw-skills/moltbook-reporter python3 auto_run.py
"""
from __future__ import annotations

import os
import logging

from reporter import post_update
from auto_solve_verification import submit_pending

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("moltbook-auto-run")


def main():
    logger.info("Auto-run: starting reporter post")
    try:
        # post_update returns a PostResult or None
        result = post_update()
        if result:
            logger.info("Posted to Moltbook; post_id=%s", result.post_id)
        else:
            logger.info("No post made (dry-run or skipped)")
    except Exception as exc:
        logger.error("Reporter post failed: %s", exc)

    logger.info("Auto-run: attempting to solve pending verification (if any)")
    try:
        submit_pending()
    except Exception as exc:
        logger.error("Auto-solve failed: %s", exc)


if __name__ == "__main__":
    main()
