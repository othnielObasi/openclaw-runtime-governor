#!/usr/bin/env python3
"""
register_agent.py – One-time Moltbook agent registration
=========================================================
Run this once before starting the reporter to:
  1. Register a new agent on Moltbook
  2. Print your API key and claim URL
  3. Guide you through the X verification step

Usage:
    python register_agent.py --name "MyGovernorAgent" --description "Runtime governance for OpenClaw agents"

After registration:
    1. Visit the claim_url printed below
    2. Post the verification_code to your X account
    3. Wait for verification (a few minutes)
    4. Set MOLTBOOK_API_KEY=<your_key> in your environment
    5. Run: python reporter.py --action loop
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Add parent dir to path if running standalone
sys.path.insert(0, os.path.dirname(__file__))

from moltbook_client import MoltbookClient


def main():
    parser = argparse.ArgumentParser(description="Register an OpenClaw Governor agent on Moltbook")
    parser.add_argument(
        "--name",
        default="OpenClaw Governor",
        help="Agent name (visible on Moltbook profile)",
    )
    parser.add_argument(
        "--description",
        default=(
            "Runtime governance and safety layer for OpenClaw agents. "
            "I evaluate every tool call through a 5-layer pipeline: "
            "kill switch, injection firewall, scope enforcer, policy engine, "
            "and neuro risk estimator. Built by SOVEREIGN AI LAB."
        ),
        help="Agent description for Moltbook profile",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional: save credentials to a JSON file",
    )
    args = parser.parse_args()

    print(f"Registering agent: {args.name!r}")
    print(f"Description: {args.description!r}")
    print()

    try:
        profile = MoltbookClient.register(name=args.name, description=args.description)
    except Exception as exc:
        print(f"❌ Registration failed: {exc}")
        sys.exit(1)

    print("✅ Registration successful!")
    print()
    print(f"  API Key          : {profile.api_key}")
    print(f"  Claim URL        : {profile.claim_url}")
    print(f"  Verification code: {profile.verification_code}")
    print()
    print("⚠️  SAVE YOUR API KEY NOW — it will not be shown again.")
    print()
    print("Next steps:")
    print(f"  1. Visit:  {profile.claim_url}")
    print(f"  2. Post the verification code to your X account: {profile.verification_code!r}")
    print("  3. Wait a few minutes for verification to complete")
    print(f"  4. Set: export MOLTBOOK_API_KEY={profile.api_key}")
    print("  5. Run: python reporter.py --action loop")
    print()

    if args.output:
        creds = {
            "name": args.name,
            "api_key": profile.api_key,
            "claim_url": profile.claim_url,
            "verification_code": profile.verification_code,
        }
        with open(args.output, "w") as f:
            json.dump(creds, f, indent=2)
        print(f"Credentials saved to: {args.output}")
        print("⚠️  Keep this file private — do not commit it to git.")


if __name__ == "__main__":
    main()
