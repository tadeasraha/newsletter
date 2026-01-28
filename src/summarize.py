#!/usr/bin/env python3
import os
import logging
import json
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

USE_API = os.getenv("OPENAI_USE_API", "1") not in ("0", "false", "False")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")  # doporučený kompromis cena/kvalita

def _call_openai_chat(prompt: str) -> Optional[str]:
    if not USE_API or not OPENAI_API_KEY:
        return None
    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        resp = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role":"system","content":"You extract structured items from an email and output VALID JSON ONLY."},
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
    links = re.findall(r'https?://[^\s\'"<>]+', html or text)
    seen = set()
    for i, link in enumerate(links):
        if link in seen:
            continue
        seen.add(link)
        items.append({
            "title": f"Odkaz #{i+1}",
            "summary": link,
            "link": link,
            "full_text": link
        })
    paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    for i, p in enumerate(paras[:5]):
        items.append({
            "title": f"Odstavec #{i+1}",
            "summary": (p[:200] + ("…" if len(p) > 200 else "")),
            "link": None,
            "full_text": p
        })
    if not items:
        items.append({
            "title": "Obsah",
            "summary": (text or "")[:200],
            "link": None,
            "full_text": text or html or ""
        })
    return items

def extract_items_from_message(subject: str, frm: str, text: str, html: str, uid: str) -> List[Dict[str, Any]]:
    prompt = (
        "Extract structured items from this email and output valid JSON array. "
        "Each object must have: title (short), summary (one-line), full_text (full content), link (url or null). "
        "Ignore boilerplate like 'view in browser', 'unsubscribe', 'manage your subscription'. "
        "Preserve the original language of each extracted piece (do not translate).\n\n"
        "Email subject:\n" + (subject or "") + "\n\n"
        "From:\n" + (frm or "") + "\n\n"
        "Plain text:\n" + (text or "")[:20000] + "\n\n"
        "HTML:\n" + (html or "")[:20000] + "\n\n"
        "Return JSON only."
    )

    logger.debug("Calling OpenAI for uid %s (model=%s)", uid, OPENAI_MODEL)
    resp = _call_openai_chat(prompt)
    if not resp:
        logger.debug("OpenAI unavailable or failed, using naive extractor for uid %s", uid)
        return _naive_extract(text, html)
    try:
        m = re.search(r'(\[.*\])', resp, flags=re.S)
        json_text = m.group(1) if m else resp
        data = json.loads(json_text)
        items = []
        for it in data:
            title = it.get("title") or it.get("name") or "Položka"
            summary = it.get("summary") or ""
            full_text = it.get("full_text") or it.get("content") or ""
            link = it.get("link") if it.get("link") else None
            items.append({"title": title, "summary": summary, "full_text": full_text, "link": link})
        if items:
            return items
    except Exception as e:
        logger.warning("Failed to parse OpenAI JSON, falling back: %s", e)
    return _naive_extract(text, html)
