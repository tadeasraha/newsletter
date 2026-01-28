#!/usr/bin/env python3
import os
import logging
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from jinja2 import Template
from typing import Optional
from src.fetch import fetch_messages_since
from src.summarize import extract_items_from_message
from src.filter import load_priority_map, get_priority_for_sender
import bleach

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PRIORITY_FILE = os.getenv("PRIORITY_FILE", "data/senders_priority.csv")
CACHE_DIR = Path(os.getenv("CACHE_DIR", "data/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {"img"}
ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "a": ["href", "title", "rel", "target"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

INDEX_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Týdenní digest</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui, -apple-system, "Segoe UI", Roboto, Arial;margin:0;padding:18px;background:#f6f7fb;color:#111}
.wrap{max-width:1100px;margin:0 auto}
.msg{background:#fff;padding:14px;border-radius:10px;margin-bottom:12px;border:1px solid #eaeef6}
.head{display:flex;justify-content:space-between;align-items:center}
.meta{color:#666;font-size:0.9rem}
.snippet{margin-top:8px;color:#222}
.detail-container{margin-top:8px}
button{background:#1a73e8;color:#fff;padding:6px 10px;border-radius:8px;border:none;cursor:pointer}
.title{font-weight:700}
a.link{color:#1a73e8}
</style></head>
<body>
<div class="wrap">
<h1>Týdenní digest</h1>
<p class="meta">Zobrazeny všechny zprávy z priority seznamu za zvolené období. Kliknutím načtěte detail (lazy load).</p>
{% for m in messages %}
<article class="msg" id="m-{{ m.uid }}" data-uid="{{ m.uid }}" data-priority="{{ m._priority }}">
  <div class="head">
    <div>
      <div class="title">{{ m.subject }}{% if m._priority %} (P{{ m._priority }}){% endif %}</div>
      <div class="meta">{{ m.from }} • {{ m.date }}</div>
    </div>
    <div><a class="link" href="messages/{{ m.uid }}.html" target="_blank">Otevřít celý e‑mail</a></div>
  </div>
  <div class="snippet">{{ m.snippet }}</div>
  <div class="detail-container" data-loaded="false">
    <button class="load-detail">Načíst rozšířené shrnutí</button>
  </div>
</article>
{% endfor %}
</div>
<script>
(function(){
  function escapeHtml(s){ if(!s) return ''; return s.replace(/[&<>"']/g, function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];});}
  function renderFullTextHtml(full_text, link){
    let out = '';
    if(link){ out += '<p><a href="'+escapeHtml(link)+'" target="_blank">'+escapeHtml(link)+'</a></p>'; }
    out += '<pre style="white-space:pre-wrap;">'+escapeHtml(full_text||'')+'</pre>';
    return out;
  }
  document.querySelectorAll('.load-detail').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const container = btn.closest('.detail-container');
      const article = btn.closest('article.msg');
      const uid = article.getAttribute('data-uid');
      if(container.getAttribute('data-loaded')==='true'){
        const details = container.querySelector('.details-rendered');
        if(details) details.style.display = details.style.display === 'none' ? '' : 'none';
        return;
      }
      btn.disabled = true; btn.textContent = 'Načítám…';
      try{
        const resp = await fetch('messages/'+uid+'.json');
        if(!resp.ok) throw new Error('Chyba při načítání detailu');
        const data = await resp.json();
        const wrapper = document.createElement('div'); wrapper.className='details-rendered';
        (data.items||[]).forEach((it,idx)=>{
          const sec = document.createElement('details');
          const summ = document.createElement('summary');
          summ.innerHTML = '<strong>'+escapeHtml(it.title)+'</strong> — <span style="color:#444">'+escapeHtml(it.summary)+'</span>';
          sec.appendChild(summ);
          const content = document.createElement('div'); content.style.padding='8px 0';
          const grid = document.createElement('div');
          grid.style.display='grid'; grid.style.gridTemplateColumns='1fr 2fr'; grid.style.gap='12px';
          const left = document.createElement('div'); left.innerHTML = '<strong>'+escapeHtml(it.title)+'</strong>';
          const right = document.createElement('div'); right.innerHTML = '<div style="color:#333">'+escapeHtml(it.summary)+'</div><div style="margin-top:8px"><a href="#" class="show-full" data-idx="'+idx+'">Zobrazit celý text</a></div>';
          grid.appendChild(left); grid.appendChild(right);
          content.appendChild(grid);
          const full = document.createElement('div'); full.className='full-text hidden'; full.style.marginTop='8px'; full.style.borderTop='1px solid #eee'; full.style.paddingTop='8px';
          full.innerHTML = renderFullTextHtml(it.full_text, it.link);
          content.appendChild(full);
          sec.appendChild(content);
          wrapper.appendChild(sec);
          right.querySelector('.show-full').addEventListener('click',(ev)=>{ ev.preventDefault(); full.classList.toggle('hidden'); });
        });
        container.appendChild(wrapper);
        container.setAttribute('data-loaded','true');
        btn.textContent = 'Skrýt / zobrazit shrnutí';
      }catch(e){
        console.error(e); btn.textContent='Chyba při načítání';
      }finally{ btn.disabled=false; }
    });
  });
})();
</script>
</body></html>
"""

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
    return bleach.clean(html_content or "", tags=list(ALLOWED_TAGS), attributes=ALLOWED_ATTRIBUTES, protocols=ALLOWED_PROTOCOLS, strip=True)

def get_week_window(now: Optional[datetime]=None):
    now = now or datetime.utcnow().replace(tzinfo=timezone.utc)
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
        logger.error("IMAP_HOST/IMAP_USER/IMAP_PASSWORD must be set in env")
        return

    priority_map = load_priority_map(PRIORITY_FILE)
    if not priority_map:
        logger.error("Priority map not found: %s", PRIORITY_FILE)
        return
    logger.info("Loaded %d priority entries", len(priority_map))

    start_dt, end_dt = get_week_window()
    logger.info("Window: %s -> %s (UTC)", start_dt.isoformat(), end_dt.isoformat())

    msgs = fetch_messages_since(IMAP_HOST, IMAP_USER, IMAP_PASSWORD, start_dt, mailbox="INBOX")
    logger.info("IMAP candidates: %d", len(msgs))

    seen = set(); unique=[]
    for m in msgs:
        mid = (m.get("message_id") or "").strip()
        key = mid if mid else m.get("fallback_hash")
        if not key:
            key = m.get("uid")
        if key in seen: continue
        seen.add(key); unique.append(m)
    logger.info("After dedupe: %d", len(unique))

    selected=[]
    for m in unique:
        pr = get_priority_for_sender(m.get("from",""), priority_map)
        if pr is None: continue
        m["_priority"]=pr
        m["html"] = sanitize_html(m.get("html",""))
        m["date"] = m["date"].astimezone(timezone.utc).isoformat()
        # snippet: first non-empty line of text or stripped html text
        snippet = (m.get("text") or "").strip().splitlines()
        m["snippet"] = snippet[0].strip() if snippet and snippet[0].strip() else (m.get("subject") or "")[:200]
        selected.append(m)
    logger.info("Selected by priority: %d", len(selected))

    selected_sorted = sorted(selected, key=lambda x: (x.get("_priority",999), -int(datetime.fromisoformat(x["date"]).timestamp())))

    out_dir = Path("data"); out_dir.mkdir(parents=True, exist_ok=True)
    messages_dir = out_dir / "messages"; messages_dir.mkdir(parents=True, exist_ok=True)

    # summarization and write per-message JSON + HTML
    for m in selected_sorted:
        uid = (m.get("message_id") or m.get("fallback_hash") or m.get("uid"))
        cached = load_cache(uid)
        if cached is not None:
            items = cached
        else:
            try:
                items = extract_items_from_message(m.get("subject",""), m.get("from",""), m.get("text",""), m.get("html",""), uid)
                # filter boilerplate items
                items = [it for it in items if not re.search(r"(?i)view in browser|unsubscribe|manage your subscription|preferences", (it.get("full_text") or "") + " " + (it.get("summary") or ""))]
            except Exception as e:
                logger.exception("Summarize failed uid=%s: %s", uid, e)
                items = []
            save_cache(uid, items)
        m["_items"] = items

        # write JSON
        j = { "subject": m.get("subject"), "from": m.get("from"), "date": m.get("date"), "priority": m.get("_priority"), "items": items }
        (messages_dir / f"{uid}.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")

        # write simple HTML backup page
        html_template = Template("<!doctype html><html><head><meta charset='utf-8'><title>{{subject}}</title></head><body><h1>{{subject}}</h1><p><strong>From:</strong> {{frm}} • <strong>Date:</strong> {{date}} • <strong>Priority:</strong> P{{_priority}}</p><hr>{% for it in items %}<h3>{{it.title}}</h3><p>{{it.summary}}</p><pre>{{it.full_text}}</pre>{% endfor %}<hr><div>{{html|safe}}</div></body></html>")
        rendered = html_template.render(subject=m.get("subject"), frm=m.get("from"), date=m.get("date"), _priority=m.get("_priority"), items=items, html=m.get("html",""))
        (messages_dir / f"{uid}.html").write_text(rendered, encoding="utf-8")

    # write index
    index_t = Template(INDEX_TEMPLATE)
    html = index_t.render(messages=selected_sorted)
    (out_dir / "test_digest.html").write_text(html, encoding="utf-8")
    logger.info("Generated %d messages. Digest saved to data/test_digest.html", len(selected_sorted))

if __name__ == "__main__":
    main()
