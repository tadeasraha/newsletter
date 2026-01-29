#!/usr/bin/env python3
import os
import logging
import json
import re
import hashlib
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
<html><head><meta charset="utf-8"><title>Newsletter Hell 1.0</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui, -apple-system, "Segoe UI", Roboto, Arial;margin:0;padding:18px;background:#f6f7fb;color:#111}
.wrap{max-width:1100px;margin:0 auto}
.header{margin-bottom:12px}
.period{color:#666;font-size:0.95rem;margin-bottom:12px}
.msg{background:#fff;padding:14px;border-radius:10px;margin-bottom:12px;border:1px solid #eaeef6}
.head{display:flex;justify-content:space-between;align-items:center}
.meta{color:#666;font-size:0.9rem}
.snippet{margin-top:8px;color:#222}
.detail-container{margin-top:8px}
button{background:#1a73e8;color:#fff;padding:6px 10px;border-radius:8px;border:none;cursor:pointer}
.title{font-weight:700}
a.link{color:#1a73e8}
.small{font-size:0.9rem;color:#666}
.details-rendered p{margin:8px 0}
.hidden{display:none}
</style></head><body>
<div class="wrap">
  <div class="header">
    <h1>Newsletter Hell 1.0</h1>
    <div class="period">Období: {{ period_start }} — {{ period_end }}</div>
  </div>
  <p class="small">Zobrazeny všechny newslettery z uvedeného týdne. Shrnutí jsou přednačtená — klikni na <strong>Rozbalit</strong> u příslušného newsletteru pro zobrazení shrnutí.</p>
{% for m in messages %}
<article class="msg" id="m-{{ m.safe_id }}" data-uid="{{ m.safe_id }}" data-priority="{{ m._priority }}">
  <div class="head">
    <div>
      <div class="title">{{ m.subject }}{% if m._priority %} (P{{ m._priority }}){% endif %}</div>
      <div class="meta">{{ m.from }} • {{ m.date }}</div>
    </div>
    <div><a class="link" href="messages/{{ m.safe_id }}.html" target="_blank">Otevřít celý e‑mail</a></div>
  </div>
  <div class="snippet">{{ m.overview }}</div>
  <div class="detail-container" data-loaded="false">
    <button class="load-detail">Rozbalit</button>
  </div>
</article>
{% endfor %}
</div>

<script>
/* PREFETCH is injected by server-side rendering as JSON */
window.PREFETCH = {{ prefetch_json | safe }};

(function(){
  function escapeHtml(s){ if(!s) return ''; return s.replace(/[&<>"']/g, function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];});}

  function renderItemHtml(it){
    var out = '';
    var summary = (it.summary || '').trim();
    if(summary){
      // split by sentences or newlines to create separate paragraphs
      var parts = summary.split(/(?<=[.!?])\s+|\n+/);
      for(var i=0;i<parts.length;i++){
        var p = parts[i].trim();
        if(!p) continue;
        var low = p.toLowerCase();
        if(low.indexOf('nezobrazuje se vám')!==-1 || low.indexOf('view in browser')!==-1 || low.indexOf('unsubscribe')!==-1) continue;
        out += '<p>'+escapeHtml(p)+'</p>';
      }
    }
    if(it.link){
      out += '<p>(<a href="'+escapeHtml(it.link)+'" target="_blank" rel="noopener noreferrer">odkaz zde</a>)</p>';
    }
    return out || '<p>Žádné nové užitečné informace.</p>';
  }

  document.querySelectorAll('.load-detail').forEach(btn=>{
    btn.addEventListener('click', (ev)=>{
      var container = btn.closest('.detail-container');
      var article = btn.closest('article.msg');
      var uid = article.getAttribute('data-uid');
      if(!window.PREFETCH) {
        console.error('No PREFETCH data available');
        btn.textContent = 'Chyba';
        return;
      }
      var data = window.PREFETCH[uid] || {overview:'', items:[]};
      if(container.getAttribute('data-loaded')==='true'){
        var details = container.querySelector('.details-rendered');
        if(details){
          var isHidden = details.style.display === 'none';
          details.style.display = isHidden ? '' : 'none';
          btn.textContent = isHidden ? 'Sbalit' : 'Rozbalit';
        }
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Načítám…';
      try{
        var wrapper = document.createElement('div'); wrapper.className = 'details-rendered';
        var items = data.items || [];
        if(items.length===0){
          wrapper.innerHTML = '<p>Žádné nové užitečné informace.</p>';
        } else {
          items.forEach(function(it, idx){
            var sec = document.createElement('details');
            var summ = document.createElement('summary');
            summ.innerHTML = '<strong>'+escapeHtml(it.title || '')+'</strong> — <span style="color:#444">'+escapeHtml((it.summary||'').slice(0,200))+'</span>';
            sec.appendChild(summ);

            var content = document.createElement('div'); content.style.padding='8px 0';
            var full = document.createElement('div'); full.className='full-text hidden'; full.style.marginTop='8px'; full.style.borderTop='1px solid #eee'; full.style.paddingTop='8px';
            full.innerHTML = renderItemHtml(it);
            content.appendChild(full);

            var linkDiv = document.createElement('div'); linkDiv.style.marginTop='8px';
            var a = document.createElement('a'); a.href='#'; a.textContent = 'Zobrazit celý text';
            a.style.cursor = 'pointer';
            a.addEventListener('click', function(e){ e.preventDefault(); full.classList.toggle('hidden'); a.textContent = full.classList.contains('hidden') ? 'Zobrazit celý text' : 'Skrýt text'; });
            linkDiv.appendChild(a);
            content.appendChild(linkDiv);

            sec.appendChild(content);
            wrapper.appendChild(sec);
          });
        }
        container.appendChild(wrapper);
        container.setAttribute('data-loaded','true');
        btn.textContent = 'Sbalit';
      }catch(e){
        console.error(e);
        btn.textContent = 'Chyba';
      }finally{
        btn.disabled = false;
      }
    });
  });
})();
</script>
</body></html>
"""

# helper functions
def safe_id_for(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="ignore")).hexdigest()

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

EXCLUDE_SUBJECT_PATTERNS = [
    r"confirm your subscription", r"confirm subscription", r"confirm email", r"verify your email",
    r"verification", r"potvrď", r"ověř", r"ověřte", r"confirm", r"verify", r"action required", r"please confirm"
]

def subject_is_excluded(subject: str) -> bool:
    s = (subject or "").lower()
    for p in EXCLUDE_SUBJECT_PATTERNS:
        if re.search(p, s):
            return True
    return False

def main():
    IMAP_HOST = os.getenv("IMAP_HOST")
    IMAP_USER = os.getenv("IMAP_USER")
    IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")
    if not (IMAP_HOST and IMAP_USER and IMAP_PASSWORD):
        logger.error("IMAP_HOST/IMAP_USER/IMAP_PASSWORD musí být nastaveny v env")
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
        if not m.get("is_newsletter"):
            continue
        if subject_is_excluded(m.get("subject","")):
            continue
        pr = get_priority_for_sender(m.get("from",""), priority_map)
        if pr is None: continue
        m["_priority"]=pr
        m["html"] = sanitize_html(m.get("html",""))
        m["date"] = m["date"].astimezone(timezone.utc).isoformat()
        selected.append(m)
    logger.info("Selected by priority & newsletter filter: %d", len(selected))

    selected_sorted = sorted(selected, key=lambda x: (x.get("_priority",999), -int(datetime.fromisoformat(x["date"]).timestamp())))

    out_dir = Path("data"); out_dir.mkdir(parents=True, exist_ok=True)
    messages_dir = out_dir / "messages"; messages_dir.mkdir(parents=True, exist_ok=True)

    prefetch_map = {}

    for m in selected_sorted:
        raw_id = (m.get("message_id") or m.get("fallback_hash") or m.get("uid"))
        safe_id = safe_id_for(raw_id)
        m["safe_id"] = safe_id

        cached = load_cache(safe_id)
        if cached is not None:
            summary_obj = cached
        else:
            try:
                summary_obj = extract_items_from_message(m.get("subject",""), m.get("from",""), m.get("text",""), m.get("html",""), safe_id)
                items = [it for it in summary_obj.get("items", []) if not re.search(r"(?i)view in browser|unsubscribe|manage your subscription|preferences", (it.get("full_text") or "") + " " + (it.get("summary") or ""))]
                summary_obj["items"] = items
            except Exception as e:
                logger.exception("Summarize failed uid=%s: %s", safe_id, e)
                summary_obj = {"overview": "", "items": []}
            save_cache(safe_id, summary_obj)

        m["overview"] = summary_obj.get("overview") or ""
        m["_items"] = summary_obj.get("items") or []

        j = { "subject": m.get("subject"), "from": m.get("from"), "date": m.get("date"), "priority": m.get("_priority"), "items": m["_items"], "overview": m["overview"] }
        (messages_dir / f"{safe_id}.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")

        html_template = Template("<!doctype html><html><head><meta charset='utf-8'><title>{{subject}}</title></head><body><h1>{{subject}}</h1><p><strong>From:</strong> {{frm}} • <strong>Date:</strong> {{date}} • <strong>Priority:</strong> P{{_priority}}</p><hr><h2>Stručné shrnutí</h2>{% for it in items %}<h3>{{it.title}}</h3>{% for p in it.summary.split('\\n') %}<p>{{p}}</p>{% endfor %}<pre>{{it.full_text}}</pre>{% endfor %}<hr><div>{{html|safe}}</div></body></html>")
        rendered = html_template.render(subject=m.get("subject"), frm=m.get("from"), date=m.get("date"), _priority=m.get("_priority"), items=m["_items"], overview=m["overview"], html=m.get("html",""))
        (messages_dir / f"{safe_id}.html").write_text(rendered, encoding="utf-8")

        safe_items = []
        for it in m["_items"]:
            safe_items.append({
                "title": (it.get("title") or "")[:200],
                "summary": (it.get("summary") or "")[:1000],
                "full_text": (it.get("full_text") or "")[:4000],
                "link": it.get("link")
            })
        prefetch_map[safe_id] = {"overview": m["overview"] or "", "items": safe_items}

    index_t = Template(INDEX_TEMPLATE)
    prefetch_json = json.dumps(prefetch_map, ensure_ascii=False)
    html = index_t.render(messages=selected_sorted, period_start=start_dt.date().isoformat(), period_end=end_dt.date().isoformat(), prefetch_json=prefetch_json)
    (out_dir / "test_digest.html").write_text(html, encoding="utf-8")
    logger.info("Generated %d messages. Digest saved to data/test_digest.html", len(selected_sorted))

if __name__ == "__main__":
    main()
