#!/usr/bin/env python3
import os
import logging
import json
import re
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from jinja2 import Environment, select_autoescape
from typing import Optional
from bs4 import BeautifulSoup
from src.fetch import fetch_messages_since
from src.summarize import extract_items_from_message
from src.filter import load_priority_map, get_priority_for_sender
import bleach

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PRIORITY_FILE = os.getenv("PRIORITY_FILE", "data/senders_priority.csv")
CACHE_DIR = Path(os.getenv("CACHE_DIR", "data/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# allow common tags for sanitized HTML (we won't inline raw HTML into index)
ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "img", "table", "tr", "td", "th", "thead", "tbody", "tfoot", "style"
}
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
body{font-family:system-ui, -apple-system, "Segoe UI", Roboto, Arial;margin:0;padding:36px 18px;background:#f6f7fb;color:#111}
.wrap{max-width:1100px;margin:0 auto}
.header{margin-bottom:28px;display:flex;justify-content:space-between;align-items:center}
.period{color:#666;font-size:0.95rem;margin-bottom:0}
.controls{font-size:0.95rem;color:#333}
.controls label{margin-left:8px;display:inline-flex;align-items:center;gap:6px}
.msg{background:#fff;padding:14px;border-radius:10px;margin-bottom:12px;border:1px solid #eaeef6}
.head{display:flex;justify-content:space-between;align-items:center}
.meta{color:#666;font-size:0.9rem}
.title-row{display:flex;align-items:center;gap:10px}
.title{font-weight:700;font-size:1.05rem;cursor:pointer}
.title[role="button"]:focus{outline:3px solid #cfe3ff;border-radius:6px;padding:2px}
.snippet{display:none}
.detail-container{margin-top:8px}
button{background:#1a73e8;color:#fff;padding:6px 10px;border-radius:8px;border:none;cursor:pointer}
a.link{color:#1a73e8}
.small{font-size:0.9rem;color:#666}
.prio-square{width:12px;height:12px;display:inline-block;border-radius:2px;vertical-align:middle;margin-left:6px}
.prio-1{background:#e53935}   /* red */
.prio-2{background:#fb8c00}   /* orange */
.prio-3{background:#43a047}   /* green */
.plain-paragraph{margin:10px 0;line-height:1.5;color:#222}
.header-main{margin-bottom:18px}
h1.site-title{font-size:2.2rem;margin:0 0 10px 0}
</style></head><body>
<div class="wrap">
  <div class="header header-main">
    <div>
      <h1 class="site-title">Newsletter Hell 1.0</h1>
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
<article class="msg" id="m-{{ m.safe_id }}" data-uid="{{ m.safe_id }}" data-priority="{{ m._priority }}" data-plain="{{ m.plain_b64 }}">
  <div class="head">
    <div>
      <div class="title-row">
        <!-- title becomes the interactive element: click the title to open/close the plain text -->
        <div class="title" role="button" tabindex="0">{{ m.subject }}</div>
        {% if m._priority %}
          <span class="prio-square prio-{{ m._priority }}" title="Priority P{{ m._priority }}"></span>
        {% endif %}
      </div>
      <div class="meta">{{ m.from }} • {{ m.date }}</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <!-- removed buttons per request -->
    </div>
  </div>
  <div class="detail-container" data-loaded="false"></div>
</article>
{% endfor %}

</div>

<script>
(function(){
  function escapeHtml(s){ if(!s) return ''; return s.replace(/[&<>"']/g, function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];}); }

  // click on title toggles the plain-text rendering (decoding base64 from data-plain)
  function renderPlainForArticle(article){
    var container = article.querySelector('.detail-container');
    if(!container) return;
    // if already rendered, toggle visibility
    if(container.getAttribute('data-loaded') === 'true'){
      var details = container.querySelector('.plain-rendered');
      if(details){
        var isHidden = details.style.display === 'none';
        details.style.display = isHidden ? '' : 'none';
        return;
      }
      return;
    }
    var b64 = article.getAttribute('data-plain') || '';
    var plain = '';
    if(b64){
      try { plain = decodeURIComponent(escape(window.atob(b64))); } catch(e){ try{ plain = window.atob(b64) }catch(_){ plain = ''; } }
    }
    if(!plain) plain = 'Žádný text k zobrazení.';
    var parts = plain.split(/\n{2,}|\r\n{2,}/).map(function(p){ return p.trim(); }).filter(Boolean);
    var wrapper = document.createElement('div'); wrapper.className = 'plain-rendered';
    if(parts.length === 0){
      wrapper.innerHTML = '<p class="plain-paragraph">Žádné nové užitečné informace.</p>';
    } else {
      wrapper.innerHTML = parts.map(function(p){ return '<p class="plain-paragraph">' + escapeHtml(p) + '</p>'; }).join('');
    }
    container.appendChild(wrapper);
    container.setAttribute('data-loaded','true');
  }

  // attach listeners to titles (click + keyboard)
  function attachTitleHandlers(){
    document.querySelectorAll('.title[role="button"]').forEach(function(el){
      el.addEventListener('click', function(ev){
        var article = el.closest('article.msg');
        if(article) renderPlainForArticle(article);
      });
      el.addEventListener('keydown', function(ev){
        if(ev.key === 'Enter' || ev.key === ' '){
          ev.preventDefault();
          var article = el.closest('article.msg');
          if(article) renderPlainForArticle(article);
        }
      });
    });
  }

  // priority filter
  function applyPriorityFilter(){
    var checked = Array.from(document.querySelectorAll('.prio-filter')).filter(cb=>cb.checked).map(cb=>cb.getAttribute('data-prio'));
    document.querySelectorAll('article.msg').forEach(function(article){
      var p = article.getAttribute('data-priority') || '';
      if(p && checked.indexOf(p) === -1){
        article.style.display = 'none';
      } else {
        article.style.display = '';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function(){
    attachTitleHandlers();
    document.querySelectorAll('.prio-filter').forEach(function(cb){
      cb.addEventListener('change', applyPriorityFilter);
    });
    applyPriorityFilter();
  });

})();
</script>
</body></html>
"""

# rest of the Python code: helpers, processing and rendering (unchanged)
TECHNICAL_PATTERNS = [
    r'(?i)nezobrazuje se vám newsletter správně',
    r'(?i)if you are having trouble viewing this email',
    r'(?i)click here to view in your browser',
    r'(?i)zobrazit v prohlížeči',
    r'(?i)if you can\'t see images',
    r'(?i)view in browser',
    r'(?i)local tracking pixel',
    r'(?i)unsubscribe', r'(?i)odhlásit', r'(?i)manage your subscription', r'(?i)preferences', r'(?i)privacy policy'
]

URL_RE = re.compile(r'(https?://[^\s\'"<>]+)', re.IGNORECASE)

def _strip_technical(text: str) -> str:
    t = text or ""
    for p in TECHNICAL_PATTERNS:
        t = re.sub(p, '', t)
    lines = [ln.strip() for ln in t.splitlines()]
    useful = []
    for ln in lines:
        if not ln: continue
        if len(ln) < 10:
            continue
        if re.search(r'(?i)(unsubscribe|odhlásit|preferences|manage your subscription|privacy policy|view in browser|zobrazit v prohlížeči)', ln):
            continue
        useful.append(ln)
    return "\n\n".join(useful).strip()

def html_to_plain_text(html: str, fallback: str = "") -> str:
    if not html and fallback:
        t = fallback
    else:
        try:
            t = BeautifulSoup(html or "", "html.parser").get_text(separator="\n")
        except Exception:
            t = fallback or ""
    t = re.sub(r'\r\n', '\n', t)
    t = URL_RE.sub(lambda m: f"(odkaz zde: {m.group(1)})", t)
    t = _strip_technical(t)
    t = re.sub(r'\n{3,}', '\n\n', t).strip()
    return t

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

        # write JSON (per-message)
        j = { "subject": m.get("subject"), "from": m.get("from"), "date": m.get("date"), "priority": m.get("_priority"), "items": m["_items"], "overview": m["overview"] }
        (messages_dir / f"{safe_id}.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")

        # write per-message HTML file as backup (not inlined into index)
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

        # create plain text version (cleaned) and store base64 in message object
        plain = html_to_plain_text(raw_html or m.get("text","") or "")
        try:
            b64 = base64.b64encode(plain.encode()).decode()
        except Exception:
            b64 = ""
        m["plain_b64"] = b64

    # render index (use DD/MM/YYYY format)
    period_start = start_dt.strftime("%d/%m/%Y")
    period_end = end_dt.strftime("%d/%m/%Y")
    env = Environment(autoescape=select_autoescape(default=True))
    index_t = env.from_string(INDEX_TEMPLATE)
    html = index_t.render(messages=selected_sorted, period_start=period_start, period_end=period_end)
    (out_dir / "test_digest.html").write_text(html, encoding="utf-8")
    logger.info("Generated %d messages. Digest saved to data/test_digest.html", len(selected_sorted))

if __name__ == "__main__":
    main()
