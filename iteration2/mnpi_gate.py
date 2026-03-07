"""MNPI Gate — Pre-ingestion compliance screening.

Regex/keyword-based detection of Material Non-Public Information (MNPI).
If MNPI detected: HARD BLOCK — document never enters the knowledge base.
If clear: PII scrub (regex for phone, email, addresses) then continue.

All screening decisions are logged to the mnpi_audit table.
"""

import re
from iteration2.state import MNPIScreenResult

# ---------------------------------------------------------------------------
# MNPI detection patterns
# ---------------------------------------------------------------------------

MNPI_PATTERNS = [
    re.compile(r"\b(material\s+non[\-\s]?public\s+information)\b", re.IGNORECASE),
    re.compile(r"\b(insider\s+information|insider\s+trading)\b", re.IGNORECASE),
    re.compile(r"\b(upcoming\s+acquisition|pending\s+acquisition)\b", re.IGNORECASE),
    re.compile(r"\b(unreleased\s+earnings|pre[\-\s]?announcement)\b", re.IGNORECASE),
    re.compile(r"\b(proposed\s+merger|confidential\s+deal)\b", re.IGNORECASE),
    re.compile(r"\b(not\s+yet\s+public|embargo|embargoed)\b", re.IGNORECASE),
    re.compile(r"\b(non[\-\s]?public\s+price[\-\s]?sensitive)\b", re.IGNORECASE),
    re.compile(r"\b(board\s+has\s+approved\s+but\s+not\s+announced)\b", re.IGNORECASE),
    re.compile(r"\b(unannounced\s+(deal|transaction|acquisition|merger|fundraise))\b", re.IGNORECASE),
    re.compile(r"\b(confidential|strictly\s+private)\b", re.IGNORECASE),
    re.compile(r"\b(do\s+not\s+distribute|not\s+for\s+(external\s+)?distribution)\b", re.IGNORECASE),
]

# Patterns that are common in disclaimers but NOT actually MNPI
MNPI_FALSE_POSITIVE_PATTERNS = [
    re.compile(r"disclaimer", re.IGNORECASE),
    re.compile(r"for\s+internal\s+research\s+use\s+only", re.IGNORECASE),
    re.compile(r"mock\s+(sell[\-\s]?side|report|visit)", re.IGNORECASE),
    re.compile(r"educational.*purposes", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# PII detection and scrubbing patterns
# ---------------------------------------------------------------------------

PII_PATTERNS = {
    "phone": re.compile(r"\b(\+?\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4})\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "address": re.compile(
        r"\b\d{1,5}\s+[\w\s]{3,30}(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b",
        re.IGNORECASE,
    ),
}


def screen_for_mnpi(text: str, file_name: str = "") -> MNPIScreenResult:
    """Screen a document for MNPI content.

    Returns MNPIScreenResult with is_mnpi=True if blocked.
    """
    matches = []
    for pattern in MNPI_PATTERNS:
        found = pattern.findall(text)
        if found:
            matches.extend(found)

    if matches:
        is_false_positive = any(
            fp.search(text) for fp in MNPI_FALSE_POSITIVE_PATTERNS
        )
        if not is_false_positive:
            reason = f"MNPI keywords detected: {', '.join(str(m) for m in matches[:5])}"
            return MNPIScreenResult(
                is_mnpi=True,
                confidence=min(0.5 + 0.1 * len(matches), 1.0),
                reason=reason,
                pii_entities=[],
                scrubbed_text=None,
            )

    pii_entities = []
    scrubbed = text
    for pii_type, pattern in PII_PATTERNS.items():
        found = pattern.findall(scrubbed)
        for entity in found:
            entity_str = entity if isinstance(entity, str) else entity[0]
            pii_entities.append(f"{pii_type}: {entity_str}")
            scrubbed = scrubbed.replace(entity_str, f"[{pii_type.upper()}_REDACTED]")

    return MNPIScreenResult(
        is_mnpi=False,
        confidence=0.0,
        reason=None,
        pii_entities=pii_entities,
        scrubbed_text=scrubbed if pii_entities else text,
    )
