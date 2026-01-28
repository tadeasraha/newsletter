#!/usr/bin/env python3
import os
import logging
import json
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

USE_API = os.getenv("OPENAI_USE_API", "1") not in ("0", "false", "False")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

def _call_openai_chat(prompt: str) -> Optional[str]:
    if not USE_API or not OPENAI_API_KEY:
        return None
    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        resp = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role":"system","content":"You are a precise extractor. Output STRICT JSON only."},
                {"role":"user","content":prompt}
            ],
            max_tokens=1200,
            temperature=0.0,
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.warning("OpenAI call failed: %s", e)
        return None

def _naive_extract(text: str, html: str) -> List[Dict[str, Any]]:
    items = []
    # best-effort: extract headlines (lines that look like headings) and links
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    # find up to 5 heading-like lines (short lines with capitalization or ending with ':')
    headings = [l for l in lines if (len(l) < 140 and (l.endswith(':') or l[:1].isupper()))]
    used = set()
    for i, h in enumerate(headings[:5]):
        # find following paragraph
        idx = lines.index(h)
        summary = ""
        if idx+1 < len(lines):
            summary = lines[idx+1][:300]
        items.append({"title": h.rstrip(':'), "summary": summary, "full_text": summary, "link": None})
        used.add(idx)
    # fallback: links
    links = re.findall(r'https?://[^\s\'"<>]+', html or text)
    for link in links[:5]:
        items.append({"title": "Odkaz", "summary": link, "full_text": link, "link": link})
    if not items:
        # final fallback: first paragraph
        p = lines[0] if lines else ""
        items.append({"title": p[:50] or "Obsah", "summary": p[:200], "full_text": p, "link": None})
    # ensure titles are not generic "Odkaz" for everything: if title equals link, shorten
    for it in items:
        if it["title"] == "":
            it["title"] = (it["summary"][:30] or "Obsah")
    return items

def extract_items_from_message(subject: str, frm: str, text: str, html: str, uid: str) -> List[Dict[str, Any]]:
    """
    Returns list of items: title (short, derived from content), summary (short), full_text, link|null.
    Prefer LLM extraction; fallback to heuristic.
    """
    prompt = (
        "Extract up to 12 meaningful sections from this email. RETURN VALID JSON ARRAY ONLY.\n"
        "Each item must have keys: title (VERY SHORT title derived from the actual content — e.g. a heading, CTA text, or phrase that names the section), "
        "summary (one-line summary in the SAME language as the source), full_text (the full text for that section), link (URL or null).\n"
        "Rules:\n"
        "- Do NOT invent titles like 'Link #1' or 'Paragraph #2'. Title must be taken from the email text (a heading, bolded phrase, CTA, or the clickable link text). If no good short title exists, pick a meaningful short excerpt (max 8 words).\n"
        "- Preserve original language for title/summary/full_text (do not translate).\n"
        "- Remove boilerplate (view in browser, unsubscribe, manage subscription).\n\n"
        "Email subject:\n" + (subject or "") + "\n\n"
        "From:\n" + (frm or "") + "\n\n"
        "Plain text:\n" + (text or "")[:20000] + "\n\n"
        "HTML:\n" + (html or "")[:20000] + "\n\n"
        "Output JSON only."
    )

    logger.debug("Calling OpenAI for uid %s (model=%s)", uid, OPENAI_MODEL)
    resp = _call_openai_chat(prompt)
    if not resp:
        logger.debug("OpenAI unavailable or failed for uid %s; using naive extractor", uid)
        return _naive_extract(text, html)
    try:
        m = re.search(r'(\[.*\])', resp, flags=re.S)
        json_text = m.group(1) if m else resp
        data = json.loads(json_text)
        items = []
        for it in data:
            title = it.get("title") or it.get("name") or ""
            summary = it.get("summary") or ""
            full_text = it.get("full_text") or it.get("content") or ""
            link = it.get("link") if it.get("link") else None
            # normalize and ensure not generic
            if title.strip().lower().startswith("link") and link:
                title = link.split("/")[2] if "//" in link else link
            if not title:
                title = (summary[:50] or "Obsah")
            items.append({"title": title, "summary": summary, "full_text": full_text, "link": link})
        if items:
            return items
    except Exception as e:
        logger.warning("Failed to parse OpenAI JSON for uid %s: %s", uid, e)
    return _naive_extract(text, html)
