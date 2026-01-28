#!/usr/bin/env python3
from email.utils import parseaddr
from typing import Dict
import logging
import csv

logger = logging.getLogger(__name__)

def load_priority_map(path: str) -> Dict[str, int]:
    """
    Loads CSV with header email,priority and returns dict email->int(priority).
    Emails are normalized to lowercase.
    """
    mp = {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                email = (row.get("email") or "").strip().lower()
                pr = (row.get("priority") or "").strip()
                if not email or not pr:
                    continue
                try:
                    p = int(pr)
                except ValueError:
                    continue
                mp[email] = p
    except FileNotFoundError:
        logger.warning("Priority file not found: %s", path)
    return mp

def _extract_email(from_header: str) -> str:
    """
    Extract email part from From header, normalized to lower-case.
    """
    name, email = parseaddr(from_header or "")
    return (email or "").lower()

def get_priority_for_sender(from_header: str, priority_map: Dict[str, int]):
    """
    Return priority int if sender email exactly in priority_map, otherwise None.
    """
    email = _extract_email(from_header)
    if not email:
        return None
    return priority_map.get(email)
