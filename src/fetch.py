#!/usr/bin/env python3
from imaplib import IMAP4_SSL
from email import message_from_bytes
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

def _imap_date_str(dt: datetime) -> str:
    return dt.strftime("%d-%b-%Y")

def fetch_messages_last_week(imap_host: str, imap_user: str, imap_password: str,
                             mailbox: str = "INBOX") -> List[Dict]:
    """
    Připojí se k IMAP serveru, vyhledá zprávy SINCE (7 dní) a vrátí jen ty,
    jejichž hlavička Date je >= nyní - 7 dní (timezone-aware).
    Vrací seznam dictů: {uid, subject, from, date, snippet}
    """
    since_dt = datetime.now(timezone.utc) - timedelta(days=7)
    since_date_str = _imap_date_str(since_dt)

    results = []

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
                if date_hdr:
                    try:
                        msg_dt = parsedate_to_datetime(date_hdr)
                        if msg_dt.tzinfo is None:
                            msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        msg_dt = None
                else:
                    msg_dt = None

                if msg_dt is None:
                    # fallback na INTERNALDATE
                    status2, idata = M.fetch(uid, '(INTERNALDATE)')
                    if status2 == "OK" and idata and isinstance(idata[0], tuple):
                        import re
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
                    # pokud nelze určit datum, přeskočíme
                    continue

                if msg_dt < since_dt:
                    continue

                subject = msg.get("Subject", "(no subject)")
                frm = msg.get("From", "(no from)")

                # jednoduchý snippet: první textový payload
                snippet = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ctype = part.get_content_type()
                        disp = str(part.get("Content-Disposition") or "")
                        if ctype == "text/plain" and "attachment" not in disp:
                            try:
                                snippet = part.get_payload(decode=True).decode(errors="ignore").strip()
                            except Exception:
                                snippet = ""
                            break
                else:
                    try:
                        snippet = msg.get_payload(decode=True).decode(errors="ignore").strip()
                    except Exception:
                        snippet = ""

                if snippet:
                    snippet = snippet[:300].replace("\n", " ")

                results.append({
                    "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "subject": subject,
                    "from": frm,
                    "date": msg_dt,
                    "snippet": snippet,
                })
            except Exception as e:
                logger.exception("Error fetching/parsing uid %r: %s", uid, e)
                continue

    # sort by date ascending
    results.sort(key=lambda r: r["date"])
    return results
