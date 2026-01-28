#!/usr/bin/env python3
from typing import Dict
import re

# Heuristic keyword boosts (unchanged)
KEYWORDS_PRIORITY = [
    r"\burgent\b",
    r"\bimmediate\b",
    r"\binvoice\b",
    r"\bbill\b",
    r"\bpayment\b",
    r"\bdue\b",
    r"\baction required\b",
    r"\bimportant\b",
    r"\breminder\b",
    r"\bdeadline\b",
    r"^re:"  # replies often indicate conversation
]

# Priority boost mapping: higher priority (1) -> bigger boost
PRIORITY_BOOST = {
    1: 120,
    2: 40,
    3: 0
}

def score_message(msg: Dict) -> Dict:
    """
    Calculate base score for a message (ignoring priority boost).
    Returns integer score. Consumer (main) should add PRIORITY_BOOST based on sender priority.
    """
    score = 0

    # If message appears to be a newsletter, give a small penalty (still keep if in allowed list)
    if msg.get("is_newsletter"):
        score -= 10

    subj = (msg.get("subject") or "").lower()
    snippet = (msg.get("snippet") or "").lower()

    for pat in KEYWORDS_PRIORITY:
        if re.search(pat, subj) or re.search(pat, snippet):
            score += 30
            break

    # personal sender heuristic
    frm = msg.get("from", "")
    if re.search(r"[A-Za-z0-9]+ [A-Za-z0-9]+", frm) and "@" in frm:
        score += 5

    return score
