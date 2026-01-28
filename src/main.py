#!/usr/bin/env python3
import os
import logging
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from jinja2 import Template
from typing import List, Dict, Optional
from src.fetch import fetch_messages_since
from src.summarize import extract_items_from_message
from src.filter import load_priority_map, get_priority_for_sender
import bleach

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PRIORITY_FILE = os.getenv("PRIORITY_FILE", "data/senders_priority.csv")
CACHE_DIR = Path(os.getenv("CACHE_DIR", "data/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Bleach config
ALLOWED_TAGS = bleach.sanitizer.ALLOWED_TAGS + ["img", "details", "summary", "pre"]
ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "a": ["href", "title", "rel", "target"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

# Šablona indexu (čeština) — kompletně uzavřený trojitý string
INDEX_TEMPLATE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Týdenní přehled</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
      :root{--bg:#f6f7fb;--card:#fff;--muted:#666;--accent:#1a73e8}
      body{font-family:system-ui, -apple-system, "Segoe UI", Roboto, Arial; background:var(--bg); margin:0; padding:18px; color:#111}
      .wrap{max-width:1100px;margin:0 auto}
      header{display:flex;justify-content:space-between;align-items:center;gap:12px}
      h1{margin:0;font-size:1.4rem}
      .controls{display:flex;gap:8px;align-items:center}
      .search{padding:8px;border-radius:8px;border:1px solid #e6eefc}
      .filters{display:flex;gap:8px}
      .msg{background:var(--card); padding:16px;border-radius:10px;margin-top:12px;border:1px solid #e9eef6}
      .msg.open{box-shadow:0 6px 18px rgba(20,40,80,0.06)}
      .head{display:flex;justify-content:space-between;align-items:center;gap:12px}
      .meta{color:var(--muted);font-size:0.9rem}
      .badge{background:#eef6ff;color:var(--accent);padding:6px 10px;border-radius:999px;font-weight:700}
      details{margin-top:10px;padding:8px;border-radius:8px;border:1px solid #f0f4fb;background:#fbfcff}
      summary{cursor:pointer;font-weight:700}
      img.thumb{max-width:180px;height:auto;border-radius:6px;display:block;margin-top:8px}
      .toc{margin-top:12px;background:#fff;padding:8px;border-radius:8px;border:1px solid #eef2fb}
      .small{font-size:0.85rem;color:var(--muted)}
      footer{margin-top:18px;color:var(--muted)}
      .hidden{display:none}
      button{background:var(--accent);color:#fff;border:none;padding:8px 10px;border-radius:8px;cursor:pointer}
    </style>
  </head>
  <body>
    <div class="wrap">
      <header>
        <div>
          <h1>Týdenní digest</h1>
          <div class="small">Zobrazeny všechny zprávy z vašeho priority seznamu za zvolené období. (Řazeno podle priority.)</div>
        </div>
        <div class="controls">
          <input id="q" class="search" placeholder="Hledat fulltext..." />
          <div class="filters">
            <label><input type="checkbox" class="prio-filter" value="1" checked /> P1</label>
            <label><input type="checkbox" class="prio-filter" value="2" checked /> P2</label>
            <label><input type="checkbox" class="prio-filter" value="3" checked /> P3</label>
          </div>
          <button id="toggleAll">Sbalit/rozbalit vše</button>
        </div>
      </header>

      <div class="toc small">Rychlý obsah:
        <ul>
        {% for m in messages %}
          <li><a href="#m-{{ m.uid }}">P{{ m._priority }} — {{ m.subject[:80] }}</a></li>
        {% endfor %}
        </ul>
      </div>

      {% for m in messages %}
      <article class="msg" data-priority="{{ m._priority }}" id="m-{{ m.uid }}">
        <div class="head">
          <div>
            <div style="display:flex;gap:8px;align-items:center">
              <span class="badge">P{{ m._priority }}</span>
              <div style="margin-left:6px"><strong>{{ m.subject }}</strong></div>
            </div>
            <div class="meta">{{ m.from }} • {{ m.date }} • UID: {{ m.uid }}</div>
          </div>
          <div>
            <a class="small link" href="messages/{{ m.uid }}.html" target="_blank">Otevřít celý e‑mail</a>
          </div>
        </div>

        <details open>
          <summary>Stručné shrnutí (vybrané položky)</summary>
          <div style="margin-top:8px;">
            {% if m._items %}
              {% for it in m._items %}
                <details>
                  <summary>{{ it.title }}{% if it.link %} — <a class="link" href="{{ it.link }}" target="_blank">odkaz</a>{% endif %}</summary>
                  <div style="margin-top:6px;">
                    <p><em>{{ it.summary }}</em></p>
                    <pre>{{ it.full_text }}</pre>
                  </div>
                </details>
              {% endfor %}
            {% else %}
              <p class="small">Nebylo možné extrahovat strukturované položky.</p>
            {% endif %}
            {% if m.thumb %}
              <img class="thumb" loading="lazy" src="{{ m.thumb }}" alt="Miniatura">
            {% endif %}
          </div>
        </details>

        <details>
          <summary>Plné znění (HTML)</summary>
          <div style="margin-top:8px;">
            {{ m.html | safe }}
          </div>
        </details>

        <details>
          <summary>Plain text</summary>
          <div style="margin-top:8px;">
            <pre>{{ m.text }}</pre>
          </div>
        </details>
      </article>
      {% endfor %}

      <footer>
        Vygenerováno automaticky. Pokud chcete znovu vytvořit shrnutí (re‑summarize), spusťte workflow z GitHub Actions.
      </footer>
    </div>

<script>
(function(){
  const q = document.getElementById('q');
  const toggleAll = document.getElementById('toggleAll');
  const prioChecks = Array.from(document.querySelectorAll('.prio-filter'));
  const msgs = Array.from(document.querySelectorAll('.msg'));

  function applyFilters(){
    const term = q.value.trim().toLowerCase();
    const selectedPrio = prioChecks.filter(c=>c.checked).map(c=>c.value);
    msgs.forEach(msg=>{
      const p = msg.getAttribute('data-priority');
      const txt = (msg.innerText || msg.textContent).toLowerCase();
      const matchesPrio = selectedPrio.includes(p);
      const matchesTerm = !term || txt.indexOf(term) !== -1;
      msg.style.display = (matchesPrio && matchesTerm) ? '' : 'none';
    });
  }
  q.addEventListener('input', applyFilters);
  prioChecks.forEach(c=>c.addEventListener('change', applyFilters));

  let allOpen = true;
  toggleAll.addEventListener('click', ()=>{
    document.querySelectorAll('article.msg details').forEach(d=>{
      if(allOpen) d.removeAttribute('open'); else d.setAttribute('open','');
    });
    allOpen = !allOpen;
  });

  document.querySelectorAll('article.msg details').forEach(d=>{
    d.addEventListener('toggle', ()=>{
      const el = d.closest('.msg');
      if(d.open) el.classList.add('open'); else el.classList.remove('open');
    });
  });

  applyFilters();
})();
</script>
  </body>
</html>
"""

# helpers: cache load/save
def load_cache(uid: str):
    p = CACHE_DIR / f"{uid}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def save_cache(uid: str, data):
    p = CACHE_DIR / f"{uid}.json"
    try:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.exception("Failed to write cache for uid=%s", uid)

def sanitize_html(html_content: str) -> str:
    return bleach.clean(
        html_content or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True
    )

def get_week_window(now: Optional[datetime] = None):
    # find previous Friday 08:00 (UTC) relative to now
    now = now or datetime.utcnow().replace(tzinfo=timezone.utc)
    # weekday(): Monday=0 ... Sunday=6. Friday=4
    days_ago = (now.weekday() - 4) % 7
    prev_friday = (now - timedelta(days=days_ago)).replace(hour=8, minute=0, second=0, microsecond=0)
    if prev_friday > now:
        prev_friday -= timedelta(days=7)
    start = prev_friday - timedelta(days=7)
    end = prev_friday
    return start, end

def main():
    IMAP_HOST = os.getenv("IMAP_HOST")
    IMAP_USER = os.getenv("IMAP_USER")
    IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")

    if not (IMAP_HOST and IMAP_USER and IMAP_PASSWORD):
        logger.error("IMAP_HOST/IMAP_USER/IMAP_PASSWORD musí být nastaveny v env")
        return

    priority_map = load_priority_map(PRIORITY_FILE)
    if not priority_map:
        logger.error("Nebyl nalezen priority map: %s", PRIORITY_FILE)
        return
    logger.info("Načteno %d záznamů priority", len(priority_map))

    # vyber okno (previous friday 08:00)
    start_dt, end_dt = get_week_window()
    logger.info("Fenster: od %s do %s (UTC)", start_dt.isoformat(), end_dt.isoformat())

    msgs = fetch_messages_since(IMAP_HOST, IMAP_USER, IMAP_PASSWORD, start_dt, mailbox="INBOX")
    logger.info("IMAP: nalezeno kandidátů: %d", len(msgs))

    # dedupe podle message-id (primární) nebo fallback_hash
    seen_ids = set()
    unique = []
    for m in msgs:
        mid = (m.get("message_id") or "").strip()
        key = mid if mid else m.get("fallback_hash")
        if not key:
            # safety: hash fallback is always present, but guard anyway
            key = (m.get("fallback_hash") or m.get("uid"))
        if key in seen_ids:
            continue
        seen_ids.add(key)
        unique.append(m)
    logger.info("Po deduplikaci unikátních zpráv: %d", len(unique))

    # vyber jen podle priority mapy
    selected = []
    for m in unique:
        pr = get_priority_for_sender(m.get("from", ""), priority_map)
        if pr is None:
            continue
        m["_priority"] = pr
        # sanitize HTML
        m["html"] = sanitize_html(m.get("html", ""))
        # prepare date string
        m["date"] = m["date"].astimezone(timezone.utc).isoformat()
        selected.append(m)
    logger.info("Vybráno podle priority: %d", len(selected))

    # sort strictly by priority (1 highest), tiebreaker: newer first
    selected_sorted = sorted(selected, key=lambda x: (x.get("_priority", 999), -int(datetime.fromisoformat(x["date"]).timestamp())))

    # summarization + caching (no hard limit)
    for i, m in enumerate(selected_sorted):
        uid = m.get("message_id") or m.get("fallback_hash") or m.get("uid")
        cached = load_cache(uid)
        if cached is not None:
            m["_items"] = cached
            logger.debug("Loaded cache for %s", uid)
            continue
        try:
            items = extract_items_from_message(m.get("subject",""), m.get("from",""), m.get("text",""), m.get("html",""), uid)
            # filtrovat boilerplate
            filtered = []
            for it in items:
                combined = (it.get("full_text") or "") + " " + (it.get("summary") or "")
                if re.search(r"(?i)view in browser|unsubscribe|manage your subscription|preferences", combined):
                    continue
                filtered.append(it)
            m["_items"] = filtered
            save_cache(uid, filtered)
            logger.info("Summarized uid=%s items=%d", uid, len(filtered))
        except Exception as e:
            logger.exception("Summarization failed uid=%s: %s", uid, e)
            m["_items"] = []

    # Vygenerovat HTML a uložit artifact
    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)

    index_t = Template(INDEX_TEMPLATE)
    html = index_t.render(messages=selected_sorted)
    (out_dir / "test_digest.html").write_text(html, encoding="utf-8")

    # také vytvoř per-message pages
    messages_dir = out_dir / "messages"
    messages_dir.mkdir(parents=True, exist_ok=True)
    msg_template = Template("""
    <!doctype html><html><head><meta charset="utf-8"><title>{{subject}}</title></head><body>
    <h1>{{subject}}</h1><p><strong>From:</strong> {{frm}} • <strong>Date:</strong> {{date}} • <strong>Priority:</strong> P{{_priority}}</p>
    <hr><h2>Strukturované položky</h2>
    {% for it in items %}
      <details><summary>{{it.title}}{% if it.link %} — <a href="{{it.link}}">odkaz</a>{% endif %}</summary>
      <p><em>{{it.summary}}</em></p><pre>{{it.full_text}}</pre></details>
    {% endfor %}
    <hr><h2>HTML</h2>{{html|safe}}<hr><h2>Plain</h2><pre>{{text}}</pre></body></html>
    """)
    for m in selected_sorted:
        uid = m.get("message_id") or m.get("fallback_hash") or m.get("uid")
        rendered = msg_template.render(subject=m.get("subject"),
                                       frm=m.get("from"),
                                       date=m.get("date"),
                                       _priority=m.get("_priority"),
                                       items=m.get("_items", []),
                                       html=m.get("html", ""),
                                       text=m.get("text", ""))
        (messages_dir / f"{uid}.html").write_text(rendered, encoding="utf-8")

    logger.info("Vygenerováno %d zpráv. Digest uložen do data/test_digest.html", len(selected_sorted))

if __name__ == "__main__":
    main()
