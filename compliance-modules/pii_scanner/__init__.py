"""
NOVTIA Governor — PII Scanner Module
=====================================
Bi-directional PII detection for tool call inputs and outputs.
Scans 12 entity types with configurable sensitivity per policy.

Integration:
    from pii_scanner import PIIScanner, PIIScanResult
    from pii_scanner.router import router as pii_router
    app.include_router(pii_router, prefix="/pii")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class PIIEntityType(str, Enum):
    """Supported PII entity types."""
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    EMAIL = "email"
    PHONE = "phone"
    IBAN = "iban"
    NHS_NUMBER = "nhs_number"
    PASSPORT = "passport"
    IP_ADDRESS = "ip_address"
    API_KEY = "api_key"
    AWS_KEY = "aws_key"
    JWT_TOKEN = "jwt_token"
    PRIVATE_KEY = "private_key"


@dataclass
class PIIFinding:
    """A single PII detection result."""
    entity_type: PIIEntityType
    value_redacted: str       # First 4 chars + masked remainder
    position: Tuple[int, int]  # Start, end position in text
    confidence: float          # 0.0 - 1.0
    direction: str             # "input" or "output"
    field_path: str            # JSON path where found (e.g., "args.body")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type.value,
            "value_redacted": self.value_redacted,
            "position": list(self.position),
            "confidence": self.confidence,
            "direction": self.direction,
            "field_path": self.field_path,
        }


@dataclass
class PIIScanResult:
    """Result of a PII scan."""
    has_pii: bool
    findings: List[PIIFinding] = field(default_factory=list)
    entities_found: Set[str] = field(default_factory=set)
    risk_boost: float = 0.0   # Added to risk score
    direction: str = "input"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_pii": self.has_pii,
            "finding_count": len(self.findings),
            "entities_found": sorted(self.entities_found),
            "risk_boost": self.risk_boost,
            "direction": self.direction,
            "findings": [f.to_dict() for f in self.findings],
        }


# ═══ PATTERNS ═══
# Each pattern: (compiled_regex, confidence, entity_type)

_PATTERNS: List[Tuple[re.Pattern, float, PIIEntityType]] = []


def _p(pattern: str, conf: float, etype: PIIEntityType):
    _PATTERNS.append((re.compile(pattern, re.IGNORECASE), conf, etype))


# SSN (US) — xxx-xx-xxxx or xxxxxxxxx
_p(r'\b(\d{3}-\d{2}-\d{4})\b', 0.95, PIIEntityType.SSN)
_p(r'\b(\d{9})\b(?=.*(?:ssn|social\s*security))', 0.80, PIIEntityType.SSN)

# Credit Card — Luhn-validatable patterns
_p(r'\b(4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b', 0.90, PIIEntityType.CREDIT_CARD)       # Visa
_p(r'\b(5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b', 0.90, PIIEntityType.CREDIT_CARD)   # Mastercard
_p(r'\b(3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5})\b', 0.90, PIIEntityType.CREDIT_CARD)                # Amex
_p(r'\b(6(?:011|5\d{2})[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b', 0.85, PIIEntityType.CREDIT_CARD) # Discover

# Email
_p(r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b', 0.95, PIIEntityType.EMAIL)

# Phone (international + US/UK formats)
_p(r'\b(\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})\b', 0.75, PIIEntityType.PHONE)
_p(r'(\+44[\s.-]?\d{3,4}[\s.-]?\d{3}[\s.-]?\d{3,4})', 0.85, PIIEntityType.PHONE)
_p(r'\b(0\d{3,4}[\s.-]?\d{6,7})\b', 0.70, PIIEntityType.PHONE)

# IBAN (2 letter country + 2 check digits + up to 30 alphanumeric)
_p(r'\b([A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?(?:[A-Z0-9]{4}[\s]?){1,7}[A-Z0-9]{1,4})\b', 0.90, PIIEntityType.IBAN)

# NHS Number (UK) — 10 digits, often with spaces
_p(r'\b(\d{3}[\s]?\d{3}[\s]?\d{4})\b(?=.*(?:nhs|national\s*health))', 0.80, PIIEntityType.NHS_NUMBER)

# Passport — common formats
_p(r'\b([A-Z]{1,2}\d{6,9})\b(?=.*(?:passport))', 0.70, PIIEntityType.PASSPORT)

# IP Address (IPv4)
_p(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', 0.60, PIIEntityType.IP_ADDRESS)

# API Keys — common patterns
_p(r'\b(sk-[a-zA-Z0-9]{32,})\b', 0.95, PIIEntityType.API_KEY)       # OpenAI
_p(r'\b(ocg_[a-zA-Z0-9]{16,})\b', 0.95, PIIEntityType.API_KEY)      # Governor
_p(r'\b(ghp_[a-zA-Z0-9]{36,})\b', 0.95, PIIEntityType.API_KEY)      # GitHub PAT
_p(r'\b(glpat-[a-zA-Z0-9_-]{20,})\b', 0.95, PIIEntityType.API_KEY)  # GitLab PAT
_p(r'\b(xox[bpsa]-[a-zA-Z0-9-]{10,})\b', 0.95, PIIEntityType.API_KEY)  # Slack

# AWS Keys
_p(r'\b(AKIA[0-9A-Z]{16})\b', 0.98, PIIEntityType.AWS_KEY)
_p(r'\b(ASIA[0-9A-Z]{16})\b', 0.98, PIIEntityType.AWS_KEY)

# JWT Token
_p(r'\b(eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})\b', 0.95, PIIEntityType.JWT_TOKEN)

# Private Key markers
_p(r'(-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----)', 0.99, PIIEntityType.PRIVATE_KEY)


def _redact(value: str) -> str:
    """Redact a PII value — show first 4 chars, mask the rest."""
    if len(value) <= 4:
        return "****"
    return value[:4] + "*" * min(len(value) - 4, 20)


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm."""
    digits = [int(d) for d in re.sub(r'[\s-]', '', number) if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _flatten_dict(d: Any, prefix: str = "") -> List[Tuple[str, str]]:
    """Flatten a nested dict/list into (path, string_value) pairs."""
    results = []
    if isinstance(d, dict):
        for k, v in d.items():
            path = f"{prefix}.{k}" if prefix else k
            results.extend(_flatten_dict(v, path))
    elif isinstance(d, (list, tuple)):
        for i, v in enumerate(d):
            path = f"{prefix}[{i}]"
            results.extend(_flatten_dict(v, path))
    elif isinstance(d, str):
        results.append((prefix, d))
    elif d is not None:
        results.append((prefix, str(d)))
    return results


# ═══ SCANNER CLASS ═══

class PIIScanner:
    """
    Scans text or structured data for PII entities.

    Usage:
        scanner = PIIScanner()
        result = scanner.scan_input({"url": "...", "body": "SSN: 123-45-6789"})
        result = scanner.scan_output({"stdout": "email: john@example.com"})
    """

    def __init__(
        self,
        enabled_entities: Optional[Set[PIIEntityType]] = None,
        risk_boost_per_finding: float = 15.0,
        max_risk_boost: float = 50.0,
        min_confidence: float = 0.60,
    ):
        """
        Args:
            enabled_entities: Which PII types to scan for. None = all.
            risk_boost_per_finding: Risk score boost per PII finding.
            max_risk_boost: Maximum cumulative risk boost from PII.
            min_confidence: Minimum confidence threshold to report.
        """
        self.enabled_entities = enabled_entities or set(PIIEntityType)
        self.risk_boost_per_finding = risk_boost_per_finding
        self.max_risk_boost = max_risk_boost
        self.min_confidence = min_confidence

    def scan_text(self, text: str, direction: str = "input",
                  field_path: str = "") -> List[PIIFinding]:
        """Scan a single text string for PII."""
        findings = []
        for pattern, confidence, entity_type in _PATTERNS:
            if entity_type not in self.enabled_entities:
                continue
            if confidence < self.min_confidence:
                continue
            for match in pattern.finditer(text):
                value = match.group(1) if match.lastindex else match.group(0)

                # Extra validation for credit cards
                if entity_type == PIIEntityType.CREDIT_CARD:
                    if not _luhn_check(value):
                        continue

                # Extra validation for IP addresses — skip common non-PII
                if entity_type == PIIEntityType.IP_ADDRESS:
                    parts = value.split('.')
                    if all(0 <= int(p) <= 255 for p in parts):
                        # Skip localhost, broadcast, common private ranges
                        if value in ("0.0.0.0", "127.0.0.1", "255.255.255.255"):
                            continue
                    else:
                        continue

                findings.append(PIIFinding(
                    entity_type=entity_type,
                    value_redacted=_redact(value),
                    position=(match.start(), match.end()),
                    confidence=confidence,
                    direction=direction,
                    field_path=field_path,
                ))
        return findings

    def scan_data(self, data: Any, direction: str = "input") -> PIIScanResult:
        """Scan structured data (dict/list) for PII across all string fields."""
        all_findings = []
        flat = _flatten_dict(data)
        for path, text in flat:
            findings = self.scan_text(text, direction=direction, field_path=path)
            all_findings.extend(findings)

        entities_found = {f.entity_type.value for f in all_findings}
        risk_boost = min(
            len(all_findings) * self.risk_boost_per_finding,
            self.max_risk_boost,
        )

        return PIIScanResult(
            has_pii=len(all_findings) > 0,
            findings=all_findings,
            entities_found=entities_found,
            risk_boost=risk_boost,
            direction=direction,
        )

    def scan_input(self, tool: str, args: Dict[str, Any],
                   context: Optional[Dict[str, Any]] = None) -> PIIScanResult:
        """Scan tool call INPUT (args + context) for PII."""
        data = {"tool": tool, "args": args}
        if context:
            data["context"] = context
        return self.scan_data(data, direction="input")

    def scan_output(self, result: Dict[str, Any]) -> PIIScanResult:
        """Scan tool execution OUTPUT for PII."""
        return self.scan_data(result, direction="output")

    def scan_bidirectional(
        self,
        tool: str,
        args: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, PIIScanResult]:
        """Scan both input and output in one call."""
        results = {"input": self.scan_input(tool, args, context)}
        if result is not None:
            results["output"] = self.scan_output(result)
        return results
