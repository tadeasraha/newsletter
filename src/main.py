import yaml
from pathlib import Path
from . import config
from .state import load_state, save_state
from .imap_ingest import fetch_new_messages
from .fetcher import fetch_url
from .generator import render_digest
from .send import send_digest_html

def load_sources():
    p = Path("config/sources.yaml")
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text()) or {}
    return data.get("sources", [])

def summarize_message(msg):
    subject = msg.get("Subject", "(bez předmětu)")
    text = ""
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/plain":
            text = part.get_content().strip()
            break
        if ctype == "text/html" and not text:
            text = part.get_content()
    summary = "\n".join(text.splitlines()[:5]).strip()
    return subject, summary

def main():
    sources = load_sources()
    if not sources:
        print("No sources configured. Add entries to config/sources.yaml")
        return
    state = load_state()
    msgs = fetch_new_messages(config, sources, state)
    items = []
    for m in msgs:
        src = m["source"]
        msg = m["msg"]
        subject, summ = summarize_message(msg)
        link = None
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(part.get_content(), "html.parser")
                a = soup.find("a", href=True)
                if a:
                    link = a['href']
                    break
        fetched = None
        if link:
            fetched = fetch_url(link, timeout=config.FETCH_TIMEOUT)
        item = {
            "priority": int(src.get("priority", config.DEFAULT_PRIORITY)),
            "title": fetched["title"] if fetched and fetched.get("title") else subject,
            "summary": (fetched["summary"] if fetched else summ)[:800],
            "link": fetched["url"] if fetched else (link or ""),
            "message_id": m["message_id"]
        }
        items.append(item)
        state.setdefault("processed_message_ids", []).append(m["message_id"])
    items.sort(key=lambda x: -x["priority"])
    if not items:
        print("No new items found.")
        save_state(state)
        return
    html = render_digest(items)
    subject = f"Shrnutí newsletterů k {__import__('datetime').datetime.now().strftime('%d/%m/%Y')}"
    send_digest_html(config.IMAP_USER, subject, html)
    save_state(state)
    print("Digest sent.")

if __name__ == "__main__":
    main()
