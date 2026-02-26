"""
rate_limit.py — Request rate limiting for security-sensitive endpoints
======================================================================
Uses slowapi to enforce per-IP rate limits on login and evaluation
endpoints, preventing brute-force attacks and abuse.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
