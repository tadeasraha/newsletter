#!/usr/bin/env python3
"""
Local, extractive summarizer and item extractor for emails.
No OpenAI calls. Returns dict: {"overview": str, "items": [ {title,summary,full_text,link}, ... ]}
Removes technical boilerplate, extracts informative paragraphs, keeps links separately (link field).
"""
import logging
import json
import re
from typing import List, Dict, Any, Optional
from html import escape
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# explicit: do not use external LLMs here
USE_API = False

TECHNICAL_PATTERNS = [
    r'(?i)nezobrazuje se vám newsletter správně',
    r'(?i)if you are having trouble viewing this email',
    r'(?i)click here to view in your browser',
    r'(?i)zobrazit v prohlížeči',
    r'(?i)if you can\'t see images',
    r'(?i)view in browser',
    r'(?i)local tracking pixel',
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
    plain = _to_plain_text(html, text)
    plain = _strip_technical(plain)
    lines = [l.strip() for l in plain.splitlines() if l.strip()]
    overview = " ".join(lines[:3])[:400] if lines else ""
    items: List[Dict[str, Any]] = []

    # paragraphs as candidates
    paragraphs = [p.strip() for p in re.split(r'\n{1,}', plain) if p.strip()]
    seen = set()
    for p in paragraphs:
        if len(items) >= 8:
            break
        if len(p) < 60:
            continue
        key = p[:80]
        if key in seen:
            continue
        seen.add(key)
        # drop boilerplate
        if re.search(r'(?i)(unsubscribe|odhlásit|manage your subscription|preferences|privacy policy|cookie)', p):
            continue
        # find link
        link_match = URL_RE.search(p)
        link = link_match.group(1) if link_match else None
        # title: first sentence or trimmed start
        sent = re.split(r'(?<=[.!?])\s+', p.strip())
        title = (sent[0] if sent else p)[:80]
        summary = (sent[0] if sent else p)[:300]
        items.append({
            "title": title,
            "summary": summary,
            "full_text": p,
            "link": link
        })

    # fallback: first sentences
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

    # normalize
    overview = _strip_technical(overview)
    for it in items:
        it["summary"] = _strip_technical(it.get("summary",""))
        it["full_text"] = _strip_technical(it.get("full_text",""))

    return {"overview": overview, "items": items}

def _call_openai_chat(prompt: str) -> Optional[str]:
    # intentionally disabled
    return None

def extract_items_from_message(subject: str, frm: str, text: str, html: str, uid: str) -> Dict[str, Any]:
    """
    Preferred local heuristic extractor; returns overview + items.
    """
    try:
        # Always use local heuristic in this deployment
        return _naive_sections(text or "", html or "")
    except Exception as e:
        logger.exception("extract_items_from_message failed: %s", e)
        overview = (" ".join((text or "").splitlines()[:3]) or "")[:400]
        return {"overview": overview, "items": [{"title": overview[:80], "summary": overview, "full_text": overview, "link": None}]}
