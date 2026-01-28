#!/usr/bin/env python3
import os
import logging
from datetime import timezone
from jinja2 import Template

from src.fetch import fetch_messages_last_week
from src.send import send_digest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def build_html_digest(messages):
    tmpl = """
    <!doctype html>
    <html>
      <head><meta charset="utf-8"><title>Weekly digest</title></head>
      <body>
        <h1>Weekly digest</h1>
        <p>Found {{ count }} messages from the last 7 days.</p>
        <ul>
        {% for m in messages %}
          <li>
            <strong>{{ m.date.isoformat() }}</strong> —
            <em>{{ m.from }}</em> — <strong>{{ m.subject }}</strong>
            <div style="margin-top:4px;color:#333">{{ m.snippet }}</div>
          </li>
        {% endfor %}
        </ul>
      </body>
    </html>
    """
    template = Template(tmpl)
    # convert datetimes to isoformat strings in template
    for m in messages:
        if hasattr(m["date"], "astimezone"):
            m["date"] = m["date"].astimezone(timezone.utc)
    return template.render(messages=messages, count=len(messages))

def main():
    # očekáváme env proměnné (nastav v Actions secrets nebo lokálně)
    IMAP_HOST = os.getenv("IMAP_HOST")
    IMAP_USER = os.getenv("IMAP_USER")
    IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")

    if not (IMAP_HOST and IMAP_USER and IMAP_PASSWORD):
        logger.error("IMAP_HOST/IMAP_USER/IMAP_PASSWORD must be set in env")
        return

    msgs = fetch_messages_last_week(IMAP_HOST, IMAP_USER, IMAP_PASSWORD, mailbox="INBOX")
    logger.info("Messages fetched: %d", len(msgs))

    html = build_html_digest(msgs)
    # dry_run True = uloží lokálně do data/test_digest.html
    send_digest(html, dry_run=True, out_path="data/test_digest.html")
    logger.info("Digest generation finished.")

if __name__ == "__main__":
    main()
