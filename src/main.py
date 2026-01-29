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

# allow common tags (we will also save raw HTML separately)
ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {"img", "table", "tr", "td", "th", "thead", "tbody", "tfoot", "style"}
ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "a": ["href", "title", "rel", "target"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto", "data"]

INDEX_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Newsletter Hell 1.0</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui, -apple-system, "Segoe UI", Roboto, Arial;margin:0;padding:18px;background:#f6f7fb;color:#111}
.wrap{max-width:1100px;margin:0 auto}
.header{margin-bottom:12px;display:flex;justify-content:space-between;align-items:center}
.period{color:#666;font-size:0.95rem;margin-bottom:0}
.controls{font-size:0.95rem;color:#333}
.controls label{margin-left:8px;display:inline-flex;align-items:center;gap:6px}
.msg{background:#fff;padding:12px;border-radius:10px;margin-bottom:12px;border:1px solid #eaeef6}
.head{display:flex;justify-content:space-between;align-items:center}
.meta{color:#666;font-size:0.9rem}
.title-row{display:flex;align-items:center;gap:10px}
.snippet{display:none}
.detail-container{margin-top:8px}
button{background:#1a73e8;color:#fff;padding:6px 10px;border-radius:8px;border:none;cursor:pointer}
.title{font-weight:700}
a.link{color:#1a73e8}
.small{font-size:0.9rem;color:#666}
.prio-square{width:12px;height:12px;display:inline-block;border-radius:2px;vertical-align:middle;margin-left:6px}
.prio-1{background:#e53935}   /* red */
.prio-2{background:#fb8c00}   /* orange */
.prio-3{background:#43a047}   /* green */
.hidden{display:none}
iframe.msg-frame{width:100%;min-height:480px;border:1px solid #ddd;border-radius:8px}
</style></head><body>
<div class="wrap">
  <div class="header">
    <div>
      <h1>Newsletter Hell 1.0</h1>
      <div class="period">Období: {{ period_start }} — {{ period_end }}</div>
    </div>
    <div class="controls">
      <strong>Dle priority</strong>
      <label><input type="checkbox" class="prio-filter" data-prio="1" checked> <span class="prio-square prio-1"></span> P1</label>
      <label><input type="checkbox" class="prio-filter" data-prio="2" checked> <span class="prio-square prio-2"></span> P2</label>
      <label><input type="checkbox" class="prio-filter" data-prio="3" checked> <span class="prio-square prio-3"></span> P3</label>
    </div>
  </div>

{% for m in messages %}
<article class="msg" id="m-{{ m.safe_id }}" data-uid="{{ m.safe_id }}" data-priority="{{ m._priority }}">
  <div class="head">
    <div>
      <div class="title-row">
        <div class="title">{{ m.subject }}</div>
        {% if m._priority %}
          <span class="prio-square prio-{{ m._priority }}" title="Priority P{{ m._priority }}"></span>
        {% endif %}
      </div>
      <div class="meta">{{ m.from }} • {{ m.date }}</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <!-- buttons swapped: Rozbalit first, then link -->
      <button class="load-detail">Rozbalit</button>
      <a class="link" href="messages/{{ m.safe_id }}.html" target="_blank">Otevřít celý e‑mail</a>
    </div>
  </div>
  <div class="detail-container" data-loaded="false"></div>
</article>
{% endfor %}
</div>

<script>
(function(){
  // Priority filter UI
  function applyPriorityFilter(){
    var checked = Array.from(document.querySelectorAll('.prio-filter'))
      .filter(cb=>cb.checked).map(cb=>cb.getAttribute('data-prio'));
    document.querySelectorAll('article.msg').forEach(function(article){
      var p = article.getAttribute('data-priority') || '';
      if(p && checked.indexOf(p) === -1){
        article.style.display = 'none';
      } else {
        article.style.display = '';
      }
    });
  }
  document.querySelectorAll('.prio-filter').forEach(function(cb){
    cb.addEventListener('change', applyPriorityFilter);
  });
  applyPriorityFilter(); // initial

  // Robustní načítání iframe s fallbacky a debug logy
  function tryLoadIframe(container, btn, uid){
    const baseHref = (function(){
      try {
        const p = window.location.pathname;
        return p.replace(/[^\/]*$/, '');
      } catch(e){ return './'; }
    })();

    const candidates = [
      'messages/' + uid + '.html',
      './messages/' + uid + '.html',
      baseHref + 'messages/' + uid + '.html',
      'data/messages/' + uid + '.html',
      './data/messages/' + uid + '.html',
      baseHref + 'data/messages/' + uid + '.html'
    ];

    let i = 0;
    function attemptNext(){
      if(i >= candidates.length){
        console.error('All iframe candidates failed for uid=' + uid, candidates);
        btn.textContent = 'Chyba při načítání';
        btn.disabled = false;
        return;
      }
      const url = candidates[i++];
      console.log('Trying iframe URL:', url);
      const iframe = document.createElement('iframe');
      iframe.className = 'msg-frame';
      iframe.style.display = 'none';
      iframe.src = url;
      let loaded = false;
      iframe.onload = function(){
        try {
          const doc = iframe.contentDocument || iframe.contentWindow.document;
          const bodyText = (doc && doc.body && doc.body.textContent || '').trim();
          // consider success if body has some text OR if cross-origin (can't read)
          if(bodyText.length === 0){
            // might still be ok (some files), but try heuristic: check HTTP status via src fetch not possible here
            // treat as success if no error event fired (but we still proceed to show)
          }
          loaded = true;
        } catch(e){
          // cross-origin or access denied -> still ok if load event fired
          loaded = true;
        }
        if(loaded){
          iframe.style.display = '';
          container.appendChild(iframe);
          btn.textContent = 'Sbalit';
          btn.disabled = false;
          container.setAttribute('data-loaded','true');
        } else {
          iframe.remove();
          attemptNext();
        }
      };
      iframe.onerror = function(){
        iframe.remove();
        attemptNext();
      };
      // append hidden to DOM so load/onerror fire
      container.appendChild(iframe);
      setTimeout(function(){
        if(!loaded){
          try { iframe.remove(); } catch(e){}
          attemptNext();
        }
      }, 3500);
    }
    attemptNext();
  }

  // Rozbalit: load full HTML into iframe (messages/<uid>.html) using robust loader
  document.querySelectorAll('.load-detail').forEach(function(btn){
    btn.addEventListener('click', function(ev){
      var container = btn.closest('.detail-container');
      var article = btn.closest('article.msg');
      var uid = article.getAttribute('data-uid');
      if(!uid) return;
      if(container.getAttribute('data-loaded') === 'true'){
        var frame = container.querySelector('iframe.msg-frame');
        if(frame){
          var isHidden = frame.style.display === 'none';
          frame.style.display = isHidden ? '' : 'none';
          btn.textContent = isHidden ? 'Sbalit' : 'Rozbalit';
        }
        return;
      }
      btn.disabled = true;
      btn.textContent = 'Načítám…';
      tryLoadIframe(container, btn, uid);
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
    cleaned = bleach.clean(html_content or "", tags=list(ALLOWED_TAGS), attributes=ALLOWED_ATTRIBUTES, protocols=ALLOWED_PROTOCOLS, strip=True)
    cleaned = re.sub(r'(?is)<script.*?>.*?</script>', '', cleaned)
    cleaned = re.sub(r'javascript:', '', cleaned, flags=re.IGNORECASE)
    return cleaned

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
        raw_html = m.get("html","") or ""
        m["raw_html"] = raw_html
        m["html"] = sanitize_html(raw_html)
        try:
            m["date"] = m["date"].astimezone(timezone.utc).isoformat()
        except Exception:
            m["date"] = str(m.get("date") or "")
        selected.append(m)
    logger.info("Selected by priority & newsletter filter: %d", len(selected))

    selected_sorted = sorted(selected, key=lambda x: (x.get("_priority",999), -int(datetime.fromisoformat(x["date"]).timestamp())))

    out_dir = Path("data"); out_dir.mkdir(parents=True, exist_ok=True)
    messages_dir = out_dir / "messages"; messages_dir.mkdir(parents=True, exist_ok=True)

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

        raw_html = m.get("raw_html") or ""
        if raw_html.strip():
            msg_html = "<!doctype html><html><head><meta charset='utf-8'><title>{}</title></head><body>{}</body></html>".format(
                (m.get("subject") or "").replace("</","</"), raw_html
            )
        else:
            msg_html = "<!doctype html><html><head><meta charset='utf-8'><title>{}</title></head><body><h1>{}</h1><pre style='white-space:pre-wrap;'>{}</pre></body></html>".format(
                (m.get("subject") or ""), (m.get("subject") or ""), (m.get("text") or "")
            )
        (messages_dir / f"{safe_id}.html").write_text(msg_html, encoding="utf-8")

    index_t = Template(INDEX_TEMPLATE)
# zobrazit období ve formátu DD/MM/YYYY (den/měsíc/rok)
period_start = start_dt.strftime("%d/%m/%Y")
period_end = end_dt.strftime("%d/%m/%Y")
html = index_t.render(messages=selected_sorted, period_start=period_start, period_end=period_end)
    (out_dir / "test_digest.html").write_text(html, encoding="utf-8")
    logger.info("Generated %d messages. Digest saved to data/test_digest.html", len(selected_sorted))

if __name__ == "__main__":
    main()
