#!/usr/bin/env python3
"""
Robust generator for newsletter digest.

Main fixes:
- Always load last 7 days (start = now - 7d, end = now).
- If sender not in priority map, assign default priority 3 (don't drop messages).
- Robust date parsing/fallback to avoid crashes in sorting.
- Write per-message JSON that includes plain_text for client fallback.
- Embed base64 plain text into data-plain using Jinja |safe so it is not HTML-escaped.
- Client JS decodes base64, unescapes entities, or fetches messages/<uid>.json fallback.
- Added "Vygenerovat PDF" button that generates a printable page (open print dialog) with
  texts of all currently visible newsletters ordered by priority (asc) then newest first.
"""
import os
import logging
import json
import re
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from jinja2 import Template
from typing import Optional
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
from src.fetch import fetch_messages_since
from src.summarize import extract_items_from_message
from src.filter import load_priority_map, get_priority_for_sender
import bleach

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PRIORITY_FILE = os.getenv("PRIORITY_FILE", "data/senders_priority.csv")
CACHE_DIR = Path(os.getenv("CACHE_DIR", "data/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

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
.header-left{display:flex;gap:12px;align-items:center}
.period{color:#666;font-size:0.95rem;margin-bottom:0}
.controls{font-size:0.95rem;color:#333;display:flex;gap:8px;align-items:center}
.controls label{margin-left:8px;display:inline-flex;align-items:center;gap:6px}
.msg{background:#fff;padding:14px;border-radius:10px;margin-bottom:12px;border:1px solid #eaeef6}
.head{display:flex;justify-content:space-between;align-items:center}
.meta{color:#666;font-size:0.9rem}
.title-row{display:flex;align-items:center;gap:10px}
.title{font-weight:700;font-size:1.05rem;cursor:pointer}
.title[role="button"]:focus{outline:3px solid #cfe3ff;border-radius:6px;padding:2px}
.snippet{display:none}
.detail-container{margin-top:8px}
a.link{color:#1a73e8}
.small{font-size:0.9rem;color:#666}
.prio-square{width:12px;height:12px;display:inline-block;border-radius:2px;vertical-align:middle;margin-left:6px}
.prio-1{background:#e53935}
.prio-2{background:#fb8c00}
.prio-3{background:#43a047}
.plain-paragraph{margin:10px 0;line-height:1.5;color:#222}
.header-main{margin-bottom:18px}
h1.site-title{font-size:2.2rem;margin:0 0 10px 0}
.btn-generate { background: #ffeb3b; border: 1px solid #f0c419; padding:8px 12px; border-radius:8px; cursor:pointer; font-weight:700; }
.print-title{font-size:18px;margin:0 0 6px 0}
.print-meta{font-size:13px;color:#555;margin:0 0 12px 0}
@media print {
  body { background: #fff; padding: 20px; }
  .msg { page-break-inside: avoid; }
}
</style></head><body>
<div class="wrap">
  <div class="header header-main">
    <div class="header-left">
      <div>
        <h1 class="site-title">Newsletter Hell 1.0</h1>
        <div class="period">Období: {{ period_start }} — {{ period_end }}</div>
      </div>
      <!-- Generate PDF button -->
      <button id="generate-pdf" class="btn-generate" title="Vygenerovat PDF ze zobrazených newsletterů">Vygenerovat PDF</button>
    </div>
    <div class="controls">
      <strong>Dle priority</strong>
      <label><input type="checkbox" class="prio-filter" data-prio="1" checked> <span class="prio-square prio-1"></span> P1</label>
      <label><input type="checkbox" class="prio-filter" data-prio="2" checked> <span class="prio-square prio-2"></span> P2</label>
      <label><input type="checkbox" class="prio-filter" data-prio="3" checked> <span class="prio-square prio-3"></span> P3</label>
    </div>
  </div>

{% for m in messages %}
<article class="msg" id="m-{{ m.safe_id }}" data-uid="{{ m.safe_id }}" data-priority="{{ m._priority }}" data-ts="{{ m._date_ts }}" data-plain='{{ m.plain_b64|safe }}' data-plain-len="{{ (m.plain_b64|default(''))|length }}">
  <div class="head">
    <div>
      <div class="title-row">
        <div class="title" role="button" tabindex="0">{{ m.subject }}</div>
        {% if m._priority %}
          <span class="prio-square prio-{{ m._priority }}" title="Priority P{{ m._priority }}"></span>
        {% endif %}
      </div>
      <div class="meta">{{ m.from }} • {{ m.date }}</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center"></div>
  </div>
  <div class="detail-container" data-loaded="false"></div>
</article>
{% endfor %}

</div>

<script>
(function(){
  // helper: robust base64 -> UTF-8 string
  function base64ToUtf8(b64){
    if(!b64) return null;
    if(b64.indexOf('&') !== -1){
      try { var ta = document.createElement('textarea'); ta.innerHTML = b64; b64 = ta.value; } catch(e){ /* ignore */ }
    }
    try {
      var bin = atob(b64);
    } catch(e){
      return null;
    }
    try {
      if(typeof TextDecoder !== 'undefined'){
        var arr = new Uint8Array(bin.length);
        for(var i=0;i<bin.length;i++){ arr[i]=bin.charCodeAt(i); }
        return new TextDecoder('utf-8').decode(arr);
      } else {
        try { return decodeURIComponent(escape(bin)); } catch(e){ return bin; }
      }
    } catch(e){
      try { return decodeURIComponent(escape(bin)); } catch(e){ return bin; }
    }
  }

  function escapeHtml(s){ if(!s) return ''; return s.replace(/[&<>"']/g, function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];}); }

  // Render preview (existing logic)
  function renderPlainForArticle(article){
    var container = article.querySelector('.detail-container');
    if(!container) return;
    if(container.getAttribute('data-loaded') === 'true'){
      var details = container.querySelector('.plain-rendered');
      if(details){
        var isHidden = details.style.display === 'none';
        details.style.display = isHidden ? '' : 'none';
        console.log('toggle plain visibility for', article.getAttribute('data-uid'), 'hidden=', isHidden);
        return;
      }
      return;
    }

    var b64 = article.getAttribute('data-plain') || '';
    if(b64 && b64.indexOf('&') !== -1){
      try { var ta = document.createElement('textarea'); ta.innerHTML = b64; b64 = ta.value; } catch(e){ console.warn('unescape failed', e); }
    }

    var plain = '';
    if(b64){
      try { plain = decodeURIComponent(escape(window.atob(b64))); console.log('decoded base64 for', article.getAttribute('data-uid')); }
      catch(e){ console.warn('base64 decode failed', e); plain = ''; }
    }

    var renderFromJsonFallback = function(){
      var uid = article.getAttribute('data-uid');
      if(!uid) return;
      var url = 'messages/' + uid + '.json';
      console.log('fetch fallback JSON', url);
      fetch(url).then(function(resp){
        if(!resp.ok) throw new Error('HTTP '+resp.status);
        return resp.json();
      }).then(function(obj){
        var text = obj.plain_text || obj.overview || (obj.items && obj.items.map(function(it){ return it.summary || it.full_text || it.title; }).join('\\n\\n')) || '';
        if(!text) text = 'Žádný text k zobrazení.';
        var parts = text.split(/\\n{2,}|\\r\\n{2,}/).map(function(p){ return p.trim(); }).filter(Boolean);
        var wrapper = document.createElement('div'); wrapper.className = 'plain-rendered';
        if(parts.length === 0){
          wrapper.innerHTML = '<p class="plain-paragraph">Žádné nové užitečné informace.</p>';
        } else {
          wrapper.innerHTML = parts.map(function(p){ return '<p class="plain-paragraph">' + escapeHtml(p) + '</p>'; }).join('');
        }
        container.appendChild(wrapper);
        container.setAttribute('data-loaded','true');
      }).catch(function(err){
        console.error('Fallback fetch failed', err);
        var wrapper = document.createElement('div'); wrapper.className = 'plain-rendered';
        wrapper.innerHTML = '<p class="plain-paragraph">Nelze načíst obsah (fallback selhal).</p>';
        container.appendChild(wrapper);
        container.setAttribute('data-loaded','true');
      });
    };

    if(plain){
      var parts = plain.split(/\\n{2,}|\\r\\n{2,}/).map(function(p){ return p.trim(); }).filter(Boolean);
      var wrapper = document.createElement('div'); wrapper.className = 'plain-rendered';
      if(parts.length === 0){
        wrapper.innerHTML = '<p class="plain-paragraph">Žádné nové užitečné informace.</p>';
      } else {
        wrapper.innerHTML = parts.map(function(p){ return '<p class="plain-paragraph">' + escapeHtml(p) + '</p>'; }).join('');
      }
      container.appendChild(wrapper);
      container.setAttribute('data-loaded','true');
      return;
    }

    renderFromJsonFallback();
  }

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

  // Build printable document from currently visible articles ordered by priority asc then newest first
  async function generatePdfLike(){
    try{
      // collect visible articles
      var articles = Array.from(document.querySelectorAll('article.msg')).filter(function(a){
        return a.style.display !== 'none';
      });
      if(articles.length === 0){
        alert('Žádné zobrazené články pro tisk/PDF.');
        return;
      }
      // sort by priority (numeric asc) then by ts (desc)
      articles.sort(function(a,b){
        var pa = parseInt(a.getAttribute('data-priority')||'999',10);
        var pb = parseInt(b.getAttribute('data-priority')||'999',10);
        if(pa !== pb) return pa - pb;
        var ta = parseInt(a.getAttribute('data-ts')||'0',10);
        var tb = parseInt(b.getAttribute('data-ts')||'0',10);
        return tb - ta;
      });

      // assemble HTML
      var docParts = [];
      docParts.push('<div style="font-family:system-ui, -apple-system, Roboto, Arial; color:#111; padding:20px;">');
      docParts.push('<h1 class="print-title">Newsletter Hell — Digest</h1>');
      docParts.push('<div class="print-meta">Vygenerováno: ' + new Date().toLocaleString() + '</div>');

      for(var i=0;i<articles.length;i++){
        var art = articles[i];
        var uid = art.getAttribute('data-uid') || '';
        var subject = art.querySelector('.title') ? art.querySelector('.title').textContent.trim() : '(bez předmětu)';
        var meta = art.querySelector('.meta') ? art.querySelector('.meta').textContent.trim() : '';
        docParts.push('<hr style="border:none;border-top:1px solid #ddd;margin:18px 0;" />');
        docParts.push('<h2 style="margin:6px 0 4px 0;font-size:16px;">' + escapeHtml(subject) + '</h2>');
        docParts.push('<div style="color:#666;font-size:12px;margin-bottom:8px;">' + escapeHtml(meta) + '</div>');

        // try decode data-plain
        var b64 = art.getAttribute('data-plain') || '';
        var text = '';
        if(b64){
          text = base64ToUtf8(b64) || '';
        }
        if(!text){
          // fallback to fetch messages/<uid>.json
          if(uid){
            try{
              // synchronous fetch sequence
              // eslint-disable-next-line no-await-in-loop
              var resp = await fetch('messages/' + uid + '.json');
              if(resp.ok){
                var obj = await resp.json();
                text = obj.plain_text || obj.overview || (obj.items && obj.items.map(function(it){ return it.summary || it.full_text || it.title; }).join('\\n\\n')) || '';
              }
            }catch(e){
              console.warn('fetch fallback failed for', uid, e);
            }
          }
        }
        if(!text) text = '(není dostupný text)';

        // split into paragraphs and escape
        var parts = text.split(/\\n{2,}|\\r\\n{2,}/).map(function(p){ return p.trim(); }).filter(Boolean);
        if(parts.length === 0){
          docParts.push('<p style="margin:8px 0;color:#222;">Žádné nové užitečné informace.</p>');
        } else {
          for(var j=0;j<parts.length;j++){
            docParts.push('<p style="margin:8px 0;color:#222;line-height:1.5;">' + escapeHtml(parts[j]) + '</p>');
          }
        }
      }
      docParts.push('</div>');
      var printable = '<!doctype html><html><head><meta charset="utf-8"><title>Newsletter Hell — PDF</title><style>body{background:#fff;color:#111;font-family:system-ui, -apple-system, Roboto, Arial;padding:20px}</style></head><body>' + docParts.join('') + '</body></html>';

      // open new window and trigger print
      var w = window.open('', '_blank');
      if(!w){
        alert('Popup blocked. Povolit popups nebo stáhnout ručně.');
        return;
      }
      w.document.open();
      w.document.write(printable);
      w.document.close();
      // wait for resources to render then call print
      w.focus();
      setTimeout(function(){ try { w.print(); } catch(e) { console.error('print failed', e); } }, 500);
    }catch(e){
      console.error('generatePdfLike failed', e);
      alert('Generování PDF selhalo: ' + (e && e.message ? e.message : e));
    }
  }

  function init(){
    attachTitleHandlers();
    document.querySelectorAll('.prio-filter').forEach(function(cb){
      cb.addEventListener('change', applyPriorityFilter);
    });
    // wire generate button
    var btn = document.getElementById('generate-pdf');
    if(btn){
      btn.addEventListener('click', function(){ generatePdfLike(); });
    }
    applyPriorityFilter();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>
</body></html>
"""

# helpers
TECHNICAL_PATTERNS = [
    r'(?i)nezobrazuje se vám newsletter správně',
    r'(?i)if you are having trouble viewing this email',
    r'(?i)click here to view in your browser',
    r'(?i)zobrazit v prohlížeči',
    r'(?i)if you can\'t see images',
    r'(?i)view in browser',
    r'(?i)local tracking pixel',
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
        if re.search(r'(?i)(unsubscribe|odhlásit|preferences|manage your subscription|privacy policy|view in browser|zobrazit v prohlíče)', ln):
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

def parse_date_to_ts(val) -> int:
    if val is None:
        return 0
    try:
        if isinstance(val, datetime):
            return int(val.astimezone(timezone.utc).timestamp())
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val)
            except Exception:
                try:
                    dt = parsedate_to_datetime(val)
                except Exception:
                    return 0
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
    except Exception:
        return 0
    return 0

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
    logger.info("Loaded %d priority entries (file: %s)", len(priority_map), PRIORITY_FILE)

    # ALWAYS last 7 days up to now
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    start_dt = now - timedelta(days=7)
    end_dt = now
    logger.info("Window: %s -> %s (UTC)", start_dt.isoformat(), end_dt.isoformat())

    msgs = fetch_messages_since(IMAP_HOST, IMAP_USER, IMAP_PASSWORD, start_dt, mailbox="INBOX")
    logger.info("IMAP candidates: %d", len(msgs))

    seen = set(); unique=[]
    for m in msgs:
        mid = (m.get("message_id") or "").strip()
        key = mid if mid else m.get("fallback_hash") or m.get("uid")
        if not key:
            continue
        if key in seen: continue
        seen.add(key); unique.append(m)
    logger.info("After dedupe: %d", len(unique))

    selected=[]
    for m in unique:
        try:
            if not m.get("is_newsletter"):
                continue
            if subject_is_excluded(m.get("subject","")):
                continue
            pr = get_priority_for_sender(m.get("from",""), priority_map)
            # if no mapping, default to lowest priority (3) instead of dropping
            if pr is None:
                pr = 3
            m["_priority"] = int(pr)
            raw_html = m.get("html","") or ""
            m["raw_html"] = raw_html
            m["html"] = sanitize_html(raw_html)
            # date normalization
            dt_val = m.get("date") or m.get("internal_date") or None
            ts = parse_date_to_ts(dt_val)
            if ts == 0:
                ts = int(datetime.utcnow().replace(tzinfo=timezone.utc).timestamp())
            m["_date_ts"] = ts
            # keep date string
            try:
                if isinstance(dt_val, datetime):
                    m["date"] = dt_val.astimezone(timezone.utc).isoformat()
                elif isinstance(dt_val, str):
                    m["date"] = dt_val
                else:
                    m["date"] = datetime.utcfromtimestamp(ts).replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                m["date"] = str(dt_val or "")
            selected.append(m)
        except Exception:
            logger.exception("Skipping message during selection: %s", m.get("subject"))

    logger.info("Selected by priority & newsletter filter: %d", len(selected))

    # sort by priority asc, then newest first
    selected_sorted = sorted(selected, key=lambda x: (x.get("_priority", 999), -int(x.get("_date_ts", 0))))

    out_dir = Path("data"); out_dir.mkdir(parents=True, exist_ok=True)
    messages_dir = out_dir / "messages"; messages_dir.mkdir(parents=True, exist_ok=True)

    for m in selected_sorted:
        raw_id = (m.get("message_id") or m.get("fallback_hash") or m.get("uid") or "")
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

        # create plain text (cleaned) and base64 encode
        raw_html = m.get("raw_html") or ""
        plain = html_to_plain_text(raw_html or m.get("text","") or "")
        try:
            b64 = base64.b64encode(plain.encode("utf-8")).decode("ascii")
        except Exception:
            b64 = ""
        m["plain_b64"] = b64

        # write per-message JSON (include plain_text for fallback)
        j = {
            "subject": m.get("subject"),
            "from": m.get("from"),
            "date": m.get("date"),
            "priority": m.get("_priority"),
            "items": m["_items"],
            "overview": m["overview"],
            "plain_text": plain
        }
        (messages_dir / f"{safe_id}.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")

        # write per-message HTML file as backup
        if raw_html.strip():
            msg_html = "<!doctype html><html><head><meta charset='utf-8'><title>{}</title></head><body>{}</body></html>".format(
                (m.get("subject") or "").replace("</","</"), raw_html
            )
        else:
            msg_html = "<!doctype html><html><head><meta charset='utf-8'><title>{}</title></head><body><h1>{}</h1><pre style='white-space:pre-wrap;'>{}</pre></body></html>".format(
                (m.get("subject") or ""), (m.get("subject") or ""), (m.get("text") or "")
            )
        (messages_dir / f"{safe_id}.html").write_text(msg_html, encoding="utf-8")

    # render index
    period_start = start_dt.strftime("%d/%m/%Y")
    period_end = end_dt.strftime("%d/%m/%Y")
    index_t = Template(INDEX_TEMPLATE)
    html = index_t.render(messages=selected_sorted, period_start=period_start, period_end=period_end)
    (out_dir / "test_digest.html").write_text(html, encoding="utf-8")
    logger.info("Generated %d messages. Digest saved to data/test_digest.html", len(selected_sorted))

if __name__ == "__main__":
    main()
