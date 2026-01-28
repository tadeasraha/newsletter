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
                {"role":"system","content":"You extract a concise overview and structured sections from an email. Output VALID JSON only."},
                {"role":"user","content":prompt}
            ],
            max_tokens=1200,
            temperature=0.0,
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.warning("OpenAI call failed: %s", e)
        return None

def _naive_sections(text: str, html: str) -> Dict[str, Any]:
    # fallback: create small overview and up to 6 sections from paragraphs/links
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    overview = " ".join(lines[:3])[:300] if lines else ""
    items = []
    # headings: short lines ending with ':' or short caps-like
    headings = [l for l in lines if (len(l) < 140 and (l.endswith(':') or l[:1].isupper()))]
    used = set()
    for i, h in enumerate(headings[:5]):
        idx = lines.index(h)
        summary = lines[idx+1][:300] if idx+1 < len(lines) else ""
        items.append({"title": h.rstrip(':'), "summary": summary, "full_text": summary, "link": None})
        used.add(idx)
    # links
    links = re.findall(r'https?://[^\s\'"<>]+', html or text)
    for link in links[:3]:
        items.append({"title": link.split('/')[-1] or link, "summary": link, "full_text": link, "link": link})
    if not items and lines:
        p = lines[0]
        items.append({"title": p[:40], "summary": p[:200], "full_text": p, "link": None})
    return {"overview": overview, "items": items}

def extract_items_from_message(subject: str, frm: str, text: str, html: str, uid: str) -> Dict[str, Any]:
    """
    Return dict: { "overview": "...", "items": [ {title, summary, full_text, link}, ... ] }
    Prefer LLM extraction; fallback to heuristics.
    """
    prompt = (
        "Extract a concise OVERVIEW (one short paragraph) of the entire email and up to 12 meaningful sections. "
        "Return VALID JSON only, with this exact structure:\n"
        "{\n  \"overview\": \"...\",\n  \"items\": [ {\"title\":\"...\",\"summary\":\"...\",\"full_text\":\"...\",\"link\":<url or null>}, ... ]\n}\n\n"
        "Rules:\n"
        "- The overview must briefly summarize the whole email content in the ORIGINAL LANGUAGE (do not translate).\n"
        "- For each item, the title must be derived from the email text (a heading, bolded phrase, CTA, link text). Do NOT use generic titles like 'Link #1' or 'Paragraph #2'. If no clear title exists, use a meaningful short excerpt (max 8 words).\n"
        "- summary is a one-line summary (same language), full_text is the content to display when user expands that section, link is a URL string or null.\n"
        "- Remove boilerplate (view in browser, unsubscribe, manage your subscription) before extracting.\n\n"
        "Email subject:\n" + (subject or "") + "\n\n"
        "From:\n" + (frm or "") + "\n\n"
        "Plain text:\n" + (text or "")[:20000] + "\n\n"
        "HTML:\n" + (html or "")[:20000] + "\n\n"
        "Output JSON only."
    )

    logger.debug("Calling OpenAI for uid %s (model=%s)", uid, OPENAI_MODEL)
    resp = _call_openai_chat(prompt)
    if not resp:
        logger.debug("OpenAI unavailable for uid %s — using fallback", uid)
        return _naive_sections(text, html)

    try:
        m = re.search(r'(\{.*\})', resp, flags=re.S)
        json_text = m.group(1) if m else resp
        data = json.loads(json_text)
        # Normalize items
        items = []
        for it in data.get("items", []):
            title = it.get("title") or ""
            summary = it.get("summary") or ""
            full_text = it.get("full_text") or it.get("content") or ""
            link = it.get("link") if it.get("link") else None
            if not title:
                # fallback short excerpt
                title = (summary[:50] or full_text[:40] or "Obsah")
            # avoid trivial titles "Link" -> use domain or path segment if link exists
            if title.strip().lower().startswith("link") and link:
                try:
                    title = link.split("//",1)[1].split("/")[0]
                except Exception:
                    pass
            items.append({"title": title, "summary": summary, "full_text": full_text, "link": link})
        overview = data.get("overview") or ""
        return {"overview": overview, "items": items}
    except Exception as e:
        logger.warning("Failed to parse OpenAI response for uid %s: %s", uid, e)
        return _naive_sections(text, html)
