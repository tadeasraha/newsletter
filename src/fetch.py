#!/usr/bin/env python3
from imaplib import IMAP4_SSL
from email import message_from_bytes
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple, Optional
import logging
import re
import html
import hashlib

logger = logging.getLogger(__name__)

def _imap_date_str(dt: datetime) -> str:
    return dt.strftime("%d-%b-%Y")

def _decode_mime_words(s: Optional[str]) -> str:
    if not s:
        return ""
    parts = decode_header(s)
    out = []
    for bytes_, enc in parts:
        try:
            if isinstance(bytes_, bytes):
                out.append(bytes_.decode(enc or "utf-8", errors="replace"))
            else:
                out.append(str(bytes_))
        except Exception:
            out.append(str(bytes_))
    return "".join(out)

def _clean_boilerplate_text(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"(?is)view (this )?in (your )?browser[:].*?$",
        r"(?is)unsubscribe[:].*?$",
        r"(?is)to unsubscribe.*?$",
        r"(?is)if you no longer wish to receive.*?$",
        r"(?is)click here to view.*?$",
        r"(?is)preferences[:].*$",
        r"(?is)manage your subscription.*?$",
    ]
    s = text
    for p in patterns:
        s = re.sub(p, "", s, flags=re.MULTILINE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _extract_text_html(msg) -> Tuple[str, str]:
    text = ""
    html_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                payload = None
            if payload is None:
                continue
            try:
                chunk = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                chunk = payload.decode(errors="ignore") if isinstance(payload, (bytes,bytearray)) else str(payload)
            if ctype == "text/plain" and not text:
                text = chunk
            elif ctype == "text/html" and not html_content:
                html_content = chunk
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            text = msg.get_payload()
    text = _clean_boilerplate_text(text or "")
    if html_content:
        html_content = re.sub(r'(?is)<a[^>]*>(view in browser|unsubscribe|manage your subscription)[^<]*</a>', '', html_content)
        html_content = re.sub(r'(?is)<!--.*?-->', '', html_content)
    else:
        html_content = "<pre style='white-space:pre-wrap;font-family:inherit;'>" + html.escape(text or "") + "</pre>"
    return (text or "", html_content or "")

def _is_newsletter(msg, text: str) -> bool:
    if msg.get("List-Unsubscribe"):
        return True
    combined = (msg.get("Subject") or "") + "\n" + (msg.get("From") or "") + "\n" + (text or "")
    if re.search(r"\bunsubscribe\b", combined, flags=re.I):
        return True
    return False

def _compute_fallback_hash(subject: str, date: datetime, text: str) -> str:
    h = hashlib.sha256()
    payload = (subject or "") + "|" + date.isoformat() + "|" + (text or "")
    h.update(payload.encode("utf-8", errors="ignore"))
    return h.hexdigest()

def fetch_messages_since(imap_host: str, imap_user: str, imap_password: str,
                         since_dt: datetime, mailbox: str = "INBOX") -> List[Dict[str, Any]]:
    """
    Připojí se k IMAP a stáhne zprávy SINCE since_dt (IMAP SINCE používá datum bez času),
    vrátí seznam dictů s fields: uid, message_id, subject, from, date (datetime), text, html, snippet, is_newsletter, fallback_hash
    """
    since_date_str = _imap_date_str(since_dt)
    results: List[Dict[str, Any]] = []

    logger.info("Connecting to IMAP %s, mailbox=%s, since=%s", imap_host, mailbox, since_date_str)
    with IMAP4_SSL(imap_host) as M:
        M.login(imap_user, imap_password)
        M.select(mailbox, readonly=True)

        status, data = M.search(None, "SINCE", since_date_str)
        if status != "OK":
            logger.error("IMAP search failed: %s", status)
            return results

        uids = data[0].split()
        logger.info("Found %d candidate messages from IMAP search", len(uids))

        for uid in uids:
            try:
                status, fetch_data = M.fetch(uid, '(RFC822)')
                if status != "OK" or not fetch_data or not isinstance(fetch_data[0], tuple):
                    continue
                raw = fetch_data[0][1]
                msg = message_from_bytes(raw)

                date_hdr = msg.get("Date")
                msg_dt = None
                if date_hdr:
                    try:
                        msg_dt = parsedate_to_datetime(date_hdr)
                        if msg_dt.tzinfo is None:
                            msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        msg_dt = None

                if msg_dt is None:
                    status2, idata = M.fetch(uid, '(INTERNALDATE)')
                    if status2 == "OK" and idata and isinstance(idata[0], tuple):
                        m = re.search(rb'INTERNALDATE "([^"]+)"', idata[0][0])
                        if m:
                            try:
                                idt = m.group(1).decode()
                                msg_dt = parsedate_to_datetime(idt)
                                if msg_dt.tzinfo is None:
                                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                            except Exception:
                                msg_dt = None

                if msg_dt is None:
                    continue

                raw_subject = msg.get("Subject", "(no subject)")
                subject = _decode_mime_words(raw_subject)
                frm = _decode_mime_words(msg.get("From", "(no from)"))

                text, html_content = _extract_text_html(msg)
                newsletter = _is_newsletter(msg, text)

                # snippet
                snippet = ""
                for line in (text or "").splitlines():
                    line = line.strip()
                    if line:
                        snippet = line
                        break
                if snippet:
                    snippet = snippet[:400]

                message_id = (msg.get("Message-ID") or msg.get("MessageID") or "").strip()
                # normalize angle brackets
                if message_id.startswith("<") and message_id.endswith(">"):
                    message_id = message_id[1:-1]
                fallback = _compute_fallback_hash(subject, msg_dt, text or "")

                results.append({
                    "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "message_id": message_id or None,
                    "fallback_hash": fallback,
                    "subject": subject,
                    "from": frm,
                    "date": msg_dt,
                    "text": text,
                    "html": html_content,
                    "snippet": snippet,
                    "is_newsletter": newsletter,
                    "raw_subject": raw_subject,
                })
            except Exception as e:
                logger.exception("Error fetching/parsing uid %r: %s", uid, e)
                continue

    results.sort(key=lambda r: r["date"])
    return results
