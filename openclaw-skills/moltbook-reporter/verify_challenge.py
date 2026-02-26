"""
verify_challenge.py — helper to submit Moltbook verification answers
Usage:
  python verify_challenge.py --answer 15.00
  python verify_challenge.py --code moltbook_verify_abc --answer 15.00

If no code is given, the script will look for ~/.config/moltbook/pending_verification.json
and submit the stored verification_code with the provided answer.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from moltbook_client import MoltbookClient


def load_pending(path: str):
    with open(path, "r") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Submit Moltbook verification answer")
    parser.add_argument("--code", help="Verification code (optional)")
    parser.add_argument("--answer", required=True, help="Answer number, e.g. 15.00")
    parser.add_argument("--credentials", help="Path to credentials json (optional)")
    args = parser.parse_args()

    verification_code = args.code
    if not verification_code:
        pending_path = os.path.expanduser("~/.config/moltbook/pending_verification.json")
        if not os.path.exists(pending_path):
            print("No pending verification found at ~/.config/moltbook/pending_verification.json and --code not provided.")
            sys.exit(2)
        pending = load_pending(pending_path)
        verification_code = pending.get("verification_code")
        print("Loaded pending challenge:")
        print(pending.get("challenge_text"))

    api_key = os.getenv("MOLTBOOK_API_KEY")
    if not api_key:
        # try credentials file
        cred_path = args.credentials or os.path.expanduser("~/.config/moltbook/credentials.json")
        if os.path.exists(cred_path):
            with open(cred_path, "r") as f:
                cred = json.load(f)
                api_key = cred.get("api_key")

    if not api_key:
        print("MOLTBOOK_API_KEY not set and no credentials.json found. Set env var or pass credentials file.")
        sys.exit(2)

    client = MoltbookClient(api_key=api_key)
    try:
        resp = client.verify(verification_code, args.answer)
        print("Verification response:")
        print(json.dumps(resp, indent=2))
        # remove pending file if exists
        pending_path = os.path.expanduser("~/.config/moltbook/pending_verification.json")
        if os.path.exists(pending_path):
            try:
                os.remove(pending_path)
            except Exception:
                pass
    except Exception as exc:
        print("Verification failed:", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
