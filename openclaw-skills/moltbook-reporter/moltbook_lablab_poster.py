#!/usr/bin/env python3
"""
Automatic Moltbook `lablab` poster for openclaw-governor.

Features:
    - Uses MOLTBOOK_API_KEY from environment (required).
    - Respects a minimum interval between posts (default 120 minutes,
      configurable via MOLTBOOK_MIN_POST_INTERVAL_MIN).
    - Optionally summarises recent runtime events from logs/openclaw-events.jsonl
      to make posts look like real OpenClaw telemetry.
    - Writes simple state to memory/moltbook-lablab-state.json to track last post.
    - Detects Moltbook verification challenges, auto-solves the obfuscated
      math problem, and calls /verify automatically (with safeguards).

Usage:
    pip install requests

    export MOLTBOOK_API_KEY="moltbook_xxx"
    # Optional:
    export MOLTBOOK_AGENT_NAME="openclaw-governor"
    export MOLTBOOK_MIN_POST_INTERVAL_MIN=120

    python moltbook_lablab_poster.py
"""

import json
import os
import random
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------- Configuration ----------

BASE_URL = "https://www.moltbook.com/api/v1"

STATE_FILE = Path("memory/moltbook-lablab-state.json")
LOG_FILE = Path("logs/openclaw-events.jsonl")

DEFAULT_MIN_INTERVAL_MINUTES = 120


@dataclass
class PosterConfig:
    api_key: str
    agent_name: str = "openclaw-governor"
    min_interval_minutes: int = DEFAULT_MIN_INTERVAL_MINUTES


class MoltbookLablabPoster:
    def __init__(self, config: PosterConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.config.api_key}",
                "User-Agent": f"{self.config.agent_name}/1.1",
            }
        )

    # ---------- State management ----------

    def _load_state(self) -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                with STATE_FILE.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"last_post_at": None, "last_post_id": None}
        return {"last_post_at": None, "last_post_id": None}

    def _save_state(self, state: Dict[str, Any]) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    @staticmethod
    def _minutes_since(iso_ts: Optional[str]) -> float:
        if not iso_ts:
            return 9999.0
        try:
            dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        except ValueError:
            return 9999.0
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() / 60.0

    # ---------- HTTP helpers ----------

    @staticmethod
    def _handle_response(resp: requests.Response) -> Dict[str, Any]:
        try:
            data = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise

        if not resp.ok or (isinstance(data, dict) and not data.get("success", True)):
            error = data.get("error") if isinstance(data, dict) else None
            hint = data.get("hint") if isinstance(data, dict) else None
            raise RuntimeError(
                f"Moltbook API error: {error or resp.text} | hint: {hint}"
            )
        return data

    # ---------- Number parsing & challenge solving ----------

    @staticmethod
    def _collapse_repeats(word: str) -> str:
        """
        Collapse repeated adjacent letters: 'thhiirrttyy' -> 'thirty'
        """
        if not word:
            return word
        result = [word[0]]
        for ch in word[1:]:
            if ch != result[-1]:
                result.append(ch)
        return "".join(result)

    @staticmethod
    def _number_word_to_value(word: str) -> Optional[int]:
        """
        Convert a normalized number word into an integer.
        Supports 0-99 which is enough for these challenges.
        """
        basic = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
        }
        tens = {
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
            "seventy": 70,
            "eighty": 80,
            "ninety": 90,
        }

        if word in basic:
            return basic[word]
        if word in tens:
            return tens[word]
        return None

    def _extract_numbers_and_operator(
        self, challenge_text: str
    ) -> Tuple[List[int], Optional[str]]:
        """
        Parse the obfuscated challenge text to find:
            - a list of numeric values (ints)
            - the first arithmetic operator (+, -, *, /)

        Strategy:
            - Lowercase
            - Keep letters, digits and +-*/; replace others with spaces.
            - Split into tokens
            - For each alphabetic token, collapse repeated letters and
              try to map to a number word.
            - For tens+units (e.g. 'thirty' 'two') combine into one number.
        """
        text = challenge_text.lower()

        # Replace any char that's not letter, digit, or +-*/ with space.
        cleaned_chars: List[str] = []
        for ch in text:
            if ch.isalpha() or ch.isdigit():
                cleaned_chars.append(ch)
            elif ch in "+-*/":
                cleaned_chars.append(f" {ch} ")
            else:
                cleaned_chars.append(" ")
        normalized = "".join(cleaned_chars)
        tokens = normalized.split()

        # Extract operator (first occurrence in original text)
        operator: Optional[str] = None
        for ch in text:
            if ch in "+-*/":
                operator = ch
                break

        # Map tokens -> numbers
        raw_values: List[Tuple[int, int]] = []  # (value, index)
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            # If token is pure digits, interpret directly
            if tok.isdigit():
                raw_values.append((int(tok), i))
                i += 1
                continue

            if tok.isalpha():
                collapsed = self._collapse_repeats(tok)
                val = self._number_word_to_value(collapsed)
                if val is not None:
                    raw_values.append((val, i))
            i += 1

        # Now combine tens + units into single numbers when adjacent
        combined: List[int] = []
        used_indices = set()
        for idx, (val, pos) in enumerate(raw_values):
            if pos in used_indices:
                continue
            # Check if this is tens (>=20 and multiple of 10),
            # and followed by units (1-9) at next position
            if val >= 20 and val % 10 == 0:
                # Find next candidate
                if idx + 1 < len(raw_values):
                    next_val, next_pos = raw_values[idx + 1]
                    if next_pos == pos + 1 and 1 <= next_val <= 9:
                        combined_val = val + next_val
                        combined.append(combined_val)
                        used_indices.add(pos)
                        used_indices.add(next_pos)
                        continue
            # Otherwise treat as standalone
            combined.append(val)
            used_indices.add(pos)

        return combined, operator

    def _solve_challenge(self, challenge_text: str) -> Optional[str]:
        """
        Solve the Moltbook math challenge and return the answer as a string
        formatted with two decimal places (e.g., "47.00").
        Returns None if it cannot safely compute the answer.
        """
        numbers, op = self._extract_numbers_and_operator(challenge_text)

        print("🔍 Parsed challenge:")
        print(f"    Raw text: {challenge_text}")
        print(f"    Numbers : {numbers}")
        print(f"    Operator: {op}")
        print()

        if op is None or len(numbers) < 2:
            print("❌ Could not reliably parse operator or numbers from challenge.")
            return None

        # Use the first two numbers in the order they appear
        a, b = numbers[0], numbers[1]

        try:
            if op == "+":
                result = a + b
            elif op == "-":
                result = a - b
            elif op == "*":
                result = a * b
            elif op == "/":
                # Protect against division by zero, though it shouldn't happen
                if b == 0:
                    print("❌ Division by zero encountered in challenge.")
                    return None
                result = a / b
            else:
                print(f"❌ Unsupported operator: {op}")
                return None
        except Exception as e:
            print(f"❌ Error computing result: {e}")
            return None

        answer_str = f"{result:.2f}"
        print(f"✅ Computed challenge answer: {a} {op} {b} = {answer_str}")
        return answer_str

    def _auto_verify(
        self, verification_code: str, challenge_text: str
    ) -> Optional[Dict[str, Any]]:
        """
        Automatically solve the challenge and POST /verify.

        Returns the verify response dict on success, or None if it couldn't solve.
        """
        answer = self._solve_challenge(challenge_text)
        if answer is None:
            print("⚠️ Auto-solver could not determine an answer; "
                  "you may need to verify manually.")
            return None

        payload = {
            "verification_code": verification_code,
            "answer": answer,
        }

        print("📬 Submitting auto-verification to Moltbook...")
        resp = self.session.post(
            f"{BASE_URL}/verify",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=20,
        )
        data = self._handle_response(resp)
        print("✅ Verification response from Moltbook:")
        print(json.dumps(data, indent=2))
        print()
        return data

    # ---------- Content generation ----------

    @staticmethod
    def _get_recent_git_activity(max_commits: int = 5) -> List[Dict[str, str]]:
        """
        Fetch recent git commits from the repo. Returns a list of dicts
        with 'hash', 'date', 'subject', and 'files_changed'.
        Works in CI where the repo is checked out.
        """
        commits: List[Dict[str, str]] = []
        try:
            log_output = subprocess.run(
                ["git", "log", f"--max-count={max_commits}",
                 "--pretty=format:%h|%aI|%s", "--no-merges"],
                capture_output=True, text=True, timeout=10,
            )
            if log_output.returncode != 0:
                return commits

            for line in log_output.stdout.strip().splitlines():
                parts = line.split("|", 2)
                if len(parts) == 3:
                    short_hash, date, subject = parts
                    # Get files changed for this commit
                    diff_output = subprocess.run(
                        ["git", "diff-tree", "--no-commit-id", "--name-only",
                         "-r", short_hash],
                        capture_output=True, text=True, timeout=10,
                    )
                    files = [f.strip() for f in diff_output.stdout.strip().splitlines()
                             if f.strip()] if diff_output.returncode == 0 else []
                    commits.append({
                        "hash": short_hash,
                        "date": date,
                        "subject": subject,
                        "files_changed": ", ".join(files[:4]) + (
                            f" (+{len(files)-4} more)" if len(files) > 4 else ""
                        ),
                    })
        except Exception:
            pass
        return commits

    @staticmethod
    def _get_repo_stats() -> Dict[str, Any]:
        """
        Get basic repo statistics for richer posts.
        """
        stats: Dict[str, Any] = {}
        try:
            # Total commits
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                stats["total_commits"] = result.stdout.strip()

            # Contributors
            result = subprocess.run(
                ["git", "shortlog", "-sn", "--no-merges", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                stats["contributors"] = len(result.stdout.strip().splitlines())

            # Last tag if any
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                stats["latest_tag"] = result.stdout.strip()
        except Exception:
            pass
        return stats

    def _summarise_recent_events(self, max_events: int = 5) -> str:
        """
        Build a summary from real git activity. Falls back to log file
        or generic message if git is unavailable.
        """
        # Try git commits first (primary source of truth in CI)
        commits = self._get_recent_git_activity(max_events)
        if commits:
            lines = []
            for c in commits:
                line = f"- `{c['hash']}` {c['subject']}"
                if c['files_changed']:
                    line += f" [{c['files_changed']}]"
                lines.append(line)
            return "\n".join(lines)

        # Fallback: try local log file
        if LOG_FILE.exists():
            try:
                raw_lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
                recent: List[str] = []
                for line in reversed(raw_lines):
                    if len(recent) >= max_events:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = evt.get("timestamp") or evt.get("time") or "unknown-time"
                    etype = evt.get("type") or evt.get("event_type") or "event"
                    desc = evt.get("summary") or evt.get("description") or ""
                    recent.append(f"- [{ts}] {etype}: {desc}")
                if recent:
                    return "\n".join(recent)
            except Exception:
                pass

        return "No recent activity found; runtime governor is idle."

    def _build_post_payload(self) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        events_text = self._summarise_recent_events()
        stats = self._get_repo_stats()

        stats_line = ""
        if stats:
            parts = []
            if "total_commits" in stats:
                parts.append(f"{stats['total_commits']} commits")
            if "contributors" in stats:
                parts.append(f"{stats['contributors']} contributors")
            if "latest_tag" in stats:
                parts.append(f"latest: {stats['latest_tag']}")
            if parts:
                stats_line = f"Repo stats: {' · '.join(parts)}"

        templates = [
            (
                "OpenClaw governor — recent development activity",
                (
                    "{agent} development update from the LabLab ecosystem at {now}.\n\n"
                    "Recent changes:\n"
                    "{events}\n\n"
                    "{stats}\n\n"
                    "Runtime governance policies, safety layers, and observability "
                    "hooks continue to evolve with each commit."
                ),
            ),
            (
                "What's new in OpenClaw runtime governor",
                (
                    "Latest activity from {agent} at {now}:\n\n"
                    "{events}\n\n"
                    "{stats}\n\n"
                    "Building policy-as-code governance for autonomous AI agents. "
                    "What safety patterns are you using in your agentic systems?"
                ),
            ),
            (
                "OpenClaw governor — commit log update",
                (
                    "{agent} project update at {now} for the `lablab` submolt.\n\n"
                    "Recent commits:\n"
                    "{events}\n\n"
                    "{stats}\n\n"
                    "Each commit strengthens the runtime control-plane — policy enforcement, "
                    "audit trails, and action-level safety constraints for AI agents."
                ),
            ),
        ]

        title, body_template = random.choice(templates)
        content = body_template.format(
            agent=self.config.agent_name,
            now=now_utc,
            events=events_text,
            stats=stats_line,
        )

        return {
            "submolt": "lablab",  # required hackathon submolt
            "title": title,
            "content": content,
        }

    # ---------- Public methods ----------

    def can_post_now(self) -> bool:
        state = self._load_state()
        minutes = self._minutes_since(state.get("last_post_at"))
        return minutes >= self.config.min_interval_minutes

    def create_post(self) -> Dict[str, Any]:
        payload = self._build_post_payload()

        print("📤 Creating Moltbook post in `lablab` submolt...")
        resp = self.session.post(
            f"{BASE_URL}/posts",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=20,
        )
        data = self._handle_response(resp)
        post = data.get("post", {})
        verification = post.get("verification") or {}

        post_id = post.get("id")
        title = post.get("title")

        print("✅ Created post draft.")
        print(f"   Post ID : {post_id}")
        print(f"   Title   : {title}")
        print(f"   Submolt : {post.get('submolt', {}).get('name', 'lablab')}")
        print()

        ver_status = post.get("verification_status") or post.get("verificationStatus")
        if verification and ver_status == "pending":
            v_code = verification.get("verification_code", "")
            challenge = verification.get("challenge_text", "")
            expires_at = verification.get("expires_at", "")
            instructions = verification.get("instructions", "")

            print("⚠️ Verification required; attempting automatic solve.")
            print(f"   Expires at (UTC): {expires_at}")
            print("   Instructions from Moltbook:")
            print(f"   {instructions}")
            print()

            verify_result = self._auto_verify(v_code, challenge)
            if not verify_result:
                print(
                    "⚠️ Auto-verification did not complete; post may remain pending. "
                    "You can still verify manually using the Moltbook docs."
                )
        else:
            print("🎉 No verification required; post should now be live in `lablab`.")

        # Update state
        state = self._load_state()
        state["last_post_at"] = datetime.now(timezone.utc).isoformat()
        state["last_post_id"] = post_id
        self._save_state(state)

        return data


# ---------- Entry point ----------


def load_config_from_env() -> PosterConfig:
    api_key = os.getenv("MOLTBOOK_API_KEY")
    if not api_key:
        raise RuntimeError("MOLTBOOK_API_KEY environment variable is not set.")

    agent_name = os.getenv("MOLTBOOK_AGENT_NAME", "openclaw-governor")

    min_interval_str = os.getenv("MOLTBOOK_MIN_POST_INTERVAL_MIN", "").strip()
    if min_interval_str:
        try:
            min_interval = int(min_interval_str)
        except ValueError:
            min_interval = DEFAULT_MIN_INTERVAL_MINUTES
    else:
        min_interval = DEFAULT_MIN_INTERVAL_MINUTES

    return PosterConfig(
        api_key=api_key,
        agent_name=agent_name,
        min_interval_minutes=min_interval,
    )


def main() -> None:
    try:
        config = load_config_from_env()
    except RuntimeError as e:
        print(f"❌ Config error: {e}")
        return

    poster = MoltbookLablabPoster(config=config)

    if not poster.can_post_now():
        print(
            f"⏱ Posting skipped: last `lablab` update was less than "
            f"{config.min_interval_minutes} minutes ago."
        )
        return

    try:
        poster.create_post()
    except Exception as e:
        print(f"❌ Failed to create Moltbook post: {e}")


if __name__ == "__main__":
    main()
