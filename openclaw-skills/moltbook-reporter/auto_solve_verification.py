"""
auto_solve_verification.py
Automatically parse and solve Moltbook verification challenges saved at
~/.config/moltbook/pending_verification.json and submit the numeric answer.

Warning: auto-solving obfuscated challenges may fail for complex puzzles.
This script uses heuristics (word-number parsing and simple operation detection)
and falls back to addition if unsure.
"""
from __future__ import annotations

import json
import os
import re
import logging
from typing import List, Optional

from moltbook_client import MoltbookClient

logger = logging.getLogger("moltbook-auto-solver")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}

_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

_OPS = {
    "add": "+", "plus": "+", "sum": "+", "combined": "+", "together": "+",
    "subtract": "-", "minus": "-", "less": "-",
    "times": "*", "multiply": "*", "product": "*", "x": "*",
    "divide": "/", "per": "/", "over": "/",
}


def words_to_number(tokens: List[str]) -> Optional[int]:
    """Convert a list of number-word tokens to an integer, supports 0-999."""
    if not tokens:
        return None
    total = 0
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in _UNITS:
            total += _UNITS[t]
        elif t in _TENS:
            value = _TENS[t]
            # look ahead for unit
            if i + 1 < len(tokens) and tokens[i + 1] in _UNITS:
                total += value + _UNITS[tokens[i + 1]]
                i += 1
            else:
                total += value
        else:
            # unknown token
            return None
        i += 1
    return total


def extract_number_groups(text: str) -> List[int]:
    """Find sequences of number words and convert them to integers."""
    # Remove non-letters and normalize
    cleaned = re.sub(r"[^a-zA-Z\s-]", " ", text).lower()
    cleaned = cleaned.replace("-", " ")
    tokens = [t for t in cleaned.split() if t]

    groups: List[int] = []
    cur: List[str] = []
    for tok in tokens:
        if tok in _UNITS or tok in _TENS:
            cur.append(tok)
        else:
            if cur:
                n = words_to_number(cur)
                if n is not None:
                    groups.append(n)
                cur = []
    if cur:
        n = words_to_number(cur)
        if n is not None:
            groups.append(n)
    return groups


def detect_operation(text: str) -> str:
    """Detect operation from text; returns one of + - * /, default +."""
    cleaned = text.lower()
    for key, op in _OPS.items():
        if key in cleaned:
            return op
    # fallback heuristics: words like "combined" or "total" -> +
    if "combined" in cleaned or "total" in cleaned or "sum" in cleaned:
        return "+"
    return "+"


def solve_challenge_text(text: str) -> Optional[str]:
    nums = extract_number_groups(text)
    if len(nums) < 2:
        logger.warning("Could not extract two numbers from challenge: %r", text)
        return None
    a, b = nums[0], nums[1]
    op = detect_operation(text)
    try:
        if op == "+":
            ans = a + b
        elif op == "-":
            ans = a - b
        elif op == "*":
            ans = a * b
        elif op == "/":
            ans = a / b if b != 0 else None
        else:
            ans = a + b
    except Exception:
        return None
    if ans is None:
        return None
    return f"{float(ans):.2f}"


def submit_pending(cred_api_key: Optional[str] = None) -> None:
    path = os.path.expanduser("~/.config/moltbook/pending_verification.json")
    if not os.path.exists(path):
        logger.info("No pending verification file found.")
        return
    with open(path, "r") as f:
        pending = json.load(f)

    code = pending.get("verification_code")
    text = pending.get("challenge_text", "")
    if not code:
        logger.error("Pending verification file missing verification_code")
        return

    answer = solve_challenge_text(text)
    if not answer:
        logger.error("Auto-solver could not determine an answer for challenge: %r", text)
        return

    api_key = cred_api_key or os.getenv("MOLTBOOK_API_KEY")
    if not api_key:
        cred_path = os.path.expanduser("~/.config/moltbook/credentials.json")
        if os.path.exists(cred_path):
            with open(cred_path, "r") as cf:
                try:
                    cred = json.load(cf)
                    api_key = cred.get("api_key")
                except Exception:
                    api_key = None
    if not api_key:
        logger.error("No Moltbook API key available to submit verification.")
        return

    client = MoltbookClient(api_key=api_key)
    try:
        resp = client.verify(code, answer)
        logger.info("Verification response: %s", resp)
        # remove pending file on success
        try:
            os.remove(path)
        except Exception:
            pass
    except Exception as exc:
        logger.error("Verification failed: %s", exc)


if __name__ == "__main__":
    submit_pending()
