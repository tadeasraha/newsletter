#!/usr/bin/env python3
"""
Local, extractive summarizer and item extractor for emails.
Replaces OpenAI usage: always uses local heuristics/fallback.
Output format: dict with "overview" and "items"; item fields: title, summary, full_text, link (or None).
Each item summary will be kept concise; links are kept but rendered as "(odkaz zde)" anchors in HTML consumers.
"""
import os
import logging
import json
import re
from typing import List, Dict, Any, Optional
from html import escape
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Force not to use any external API
USE_API = False

# Technical phrases to remove from final overview/items
TECHNICAL_PATTERNS = [
    r'(?i)nezobrazuje se vám newsletter správně',
    r'(?i)if you are having trouble viewing this email',
    r'(?i)click here to view in your browser',
    r'(?i)zobrazit v prohlížeči',
    r'(?i)if you can\'t see images',
    r'(?i)view in browser',
]

URL_RE = re.compile(r'(https?://[^\s\'"<>)+\)]+)', re.IGNORECASE)

def _strip_technical(text: str) -> str:
    t = text or ""
    for p in TECHNICAL_PATTERNS:
        t = re.sub(p, '', t)
    t = re.sub(r'\n{3,}', '\n\n', t).strip()
    return t

def _to_plain_text(html: str, fallback: str = "") -> str:
    if not html and fallback:
        return fallback
    try:
        return BeautifulSoup(html or "", "html.parser").get_text(separator="\n")
    except Exception:
        return fallback or ""

def _naive_sections(text: str, html: str) -> Dict[str, Any]:
    """
    Create an overview (one short paragraph) and up to N items using heuristics:
    - pick informative paragraphs
    - extract links as items if they look important
    """
    plain = _to_plain_text(html, text)
    plain = _strip_technical(plain)
    lines = [l.strip() for l in plain.splitlines() if l.strip()]
    overview = " ".join(lines[:3])[:400] if lines else ""
    items: List[Dict[str, Any]] = []

    # Prefer paragraphs that are long enough and contain informative tokens
    candidate_paragraphs = [p for p in re.split(r'\n{1,}', plain) if len(p.strip()) > 60]
    seen = set()
    for p in candidate_paragraphs:
        if len(items) >= 8:
            break
        key = p[:80]
        if key in seen:
            continue
        seen.add(key)
        # remove boilerplate patterns
        if re.search(r'(?i)(unsubscribe|odhlásit|manage your subscription|preferences|privacy policy)', p):
            continue
        # find the first link in paragraph (if any)
        link_match = URL_RE.search(p)
        link = link_match.group(1) if link_match else None
        # Short title: first up to 60 chars or first sentence
        sent = re.split(r'(?<=[.!?])\s+', p.strip())
        title = sent[0][:80]
        summary = sent[0][:300] if sent else p[:300]
        items.append({
            "title": title,
            "summary": summary,
            "full_text": p.strip(),
            "link": link
        })

    # If we have no items, fall back to first few sentences
    if not items and lines:
        for s in lines[:4]:
            link_match = URL_RE.search(s)
            link = link_match.group(1) if link_match else None
            items.append({
                "title": s[:80],
                "summary": s[:200],
                "full_text": s,
                "link": link
            })

    # Normalize: remove technical phrases from overview and item texts
    overview = _strip_technical(overview)
    for it in items:
        it["summary"] = _strip_technical(it["summary"])
        it["full_text"] = _strip_technical(it["full_text"])

    return {"overview": overview, "items": items}

def _call_openai_chat(prompt: str) -> Optional[str]:
    # intentionally disabled: we do not call OpenAI here
    return None

def extract_items_from_message(subject: str, frm: str, text: str, html: str, uid: str) -> Dict[str, Any]:
    """
    Return dict: { "overview": "...", "items": [ {title, summary, full_text, link}, ... ] }
    This function prefers local heuristics (_naive_sections). If an LLM were available, it could be used;
    here we always use the local fallback to avoid external API calls.
    """
    try:
        # Attempt LLM only if enabled (but USE_API is False in this deployment)
        if USE_API:
            prompt = (
                "Extract a concise OVERVIEW (one short paragraph) of the email and up to 12 meaningful sections."
                "Return valid JSON with structure {\"overview\":\"...\",\"items\":[{\"title\":\"...\",\"summary\":\"...\",\"full_text\":\"...\",\"link\":<url|null>}]}."
                "\n\nEMAIL SUBJECT:\n" + (subject or "") + "\n\nEMAIL TEXT:\n" + (text or "")
            )
            resp = _call_openai_chat(prompt)
            if resp:
                try:
                    data = json.loads(resp)
                    # Basic verification
                    if isinstance(data, dict) and "items" in data:
                        return data
                except Exception:
                    logger.warning("OpenAI returned non‑JSON or invalid structure; falling back.")
        # Local heuristic fallback
        return _naive_sections(text or "", html or "")
    except Exception as e:
        logger.exception("extract_items_from_message failed: %s", e)
        # last resort: minimal fallback
        overview = (" ".join((text or "").splitlines()[:3]) or "")[:400]
        return {"overview": overview, "items": [{"title": overview[:80], "summary": overview, "full_text": overview, "link": None}]}
