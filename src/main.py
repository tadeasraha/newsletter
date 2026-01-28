#!/usr/bin/env python3
import os
import logging
from datetime import timezone
from pathlib import Path
from jinja2 import Template
from typing import List, Dict
from collections import defaultdict

from src.fetch import fetch_messages_last_week
from src.send import save_digest_html
from src.score import score_message, PRIORITY_BOOST
from src.filter import load_priority_map, get_priority_for_sender

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOP_N = int(os.getenv("TOP_N", "20"))
PRIORITY_FILE = os.getenv("PRIORITY_FILE", "data/senders_priority.csv")

INDEX_TEMPLATE = """
<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Weekly digest</title></head>
  <body>
    <h1>Weekly digest</h1>
    <p>Showing top {{ shown }} messages (filtered by your priority list). Total selected: {{ total }}.</p>
    <ul>
    {% for m in messages %}
      <li>
        <details>
          <summary>
            <strong>[P{{ m._priority }} | score: {{ m._score_total }}] {{ m.subject }}</strong>
            — <em>{{ m.from }}</em> — {{ m.date }}
          </summary>
          <div style="margin-top:6px;">
            <div>{{ m.snippet_html | safe }}</div>
            <p><a href="messages/{{ m.uid }}.html" target="_blank">Open full message</a></p>
          </div>
        </details>
      </li>
    {% endfor %}
    </ul>
    <hr>
    <p><a href="messages/all_messages.html" target="_blank">Open page with all selected messages</a></p>
  </body>
</html>
"""

MSG_TEMPLATE = """
<!doctype html>
<html>
  <head><meta charset="utf-8"><title>{{ subject }}</title></head>
  <body>
    <h2>{{ subject }} <small>(priority: {{ _priority }}, score: {{ _score_total }})</small></h2>
    <p><strong>From:</strong> {{ frm }}</p>
    <p><strong>Date:</strong> {{ date }}</p>
    <hr>
    <h3>HTML version</h3>
    <div style="border:1px solid #ddd;padding:10px;">{{ html | safe }}</div>
    <hr>
    <h3>Plain text</h3>
    <pre style="white-space:pre-wrap;">{{ text }}</pre>
  </body>
</html>
"""

def build_html(messages: List[dict], out_dir: Path):
    out_messages_dir = out_dir / "messages"
    out_messages_dir.mkdir(parents=True, exist_ok=True)

    # write per-message pages
    msg_t = Template(MSG_TEMPLATE)
    for m in messages:
        html_body = m.get("html") or ""
        text_body = m.get("text") or ""
        rendered = msg_t.render(subject=m.get("subject"),
                                frm=m.get("from"),
                                date=m.get("date").astimezone(timezone.utc).isoformat(),
                                html=html_body,
                                text=text_body,
                                _priority=m.get("_priority"),
                                _score_total=m.get("_score_total"))
        (out_messages_dir / f"{m['uid']}.html").write_text(rendered, encoding="utf-8")

    # all messages index
    all_list_items = []
    for m in messages:
        all_list_items.append(f"<li><a href='{m['uid']}.html'>{m['date'].astimezone(timezone.utc).isoformat()} — P{m.get('_priority')} — {m['subject']} — {m['from']}</a></li>")
    all_page = "<html><body><h1>Selected messages</h1><ul>" + "\n".join(all_list_items) + "</ul></body></html>"
    (out_messages_dir / "all_messages.html").write_text(all_page, encoding="utf-8")

    # render index
    index_t = Template(INDEX_TEMPLATE)
    for m in messages:
        m["snippet_html"] = (m.get("snippet") or "")
    index_html = index_t.render(messages=messages[:min(len(messages), TOP_N)],
                                total=len(messages),
                                shown=min(len(messages), TOP_N))
    return index_html

def main():
    IMAP_HOST = os.getenv("IMAP_HOST")
    IMAP_USER = os.getenv("IMAP_USER")
    IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")

    if not (IMAP_HOST and IMAP_USER and IMAP_PASSWORD):
        logger.error("IMAP_HOST/IMAP_USER/IMAP_PASSWORD must be set in env")
        return

    priority_map = load_priority_map(PRIORITY_FILE)
    if not priority_map:
        logger.error("No priority map loaded from %s — aborting (upload data/senders_priority.csv)", PRIORITY_FILE)
        return
    logger.info("Loaded %d priority entries", len(priority_map))

    msgs = fetch_messages_last_week(IMAP_HOST, IMAP_USER, IMAP_PASSWORD, mailbox="INBOX")
    logger.info("Messages fetched from IMAP: %d", len(msgs))

    # attach priority and compute scores only for matching senders
    selected = []
    for m in msgs:
        pr = get_priority_for_sender(m.get("from", ""), priority_map)
        if pr is None:
            continue
        m["_priority"] = pr
        base = score_message(m)
        boost = PRIORITY_BOOST.get(pr, 0)
        m["_score_total"] = base + boost
        m["_ts"] = int(m["date"].timestamp())
        selected.append(m)

    logger.info("Messages matching priority list: %d", len(selected))

    # sort by score_total desc then by timestamp desc
    selected_sorted = sorted(selected, key=lambda x: (x.get("_score_total", 0), x.get("_ts", 0)), reverse=True)

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)

    index_html = build_html(selected_sorted, out_dir=out_dir)
    save_digest_html(index_html, out_path=str(out_dir / "test_digest.html"))
    logger.info("Digest generation finished. Selected messages: %d", len(selected_sorted))

if __name__ == "__main__":
    main()
