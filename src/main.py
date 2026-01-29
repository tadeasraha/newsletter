#!/usr/bin/env python3
"""
Robust generator for newsletter digest with debug support.

Features:
- Strict priority filtering (exact email or domain) unless DEBUG_INCLUDE_ALL env var is set.
- Last 7 days window.
- Generates per-message plain_text, plain_render_html and sanitized HTML and embeds base64 variants into <article>.
- Writes data/debug_selection.json to help diagnose why messages were included/skipped.
- Client-side JS tries render order: plain_render -> plain_html -> plain_text -> JSON fallback.
"""
import os
import logging
import json
import re
import hashlib
import base64
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from jinja2 import Template
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime, parseaddr
from src.fetch import fetch_messages_since
from src.summarize import extract_items_from_message
from src.filter import load_priority_map
import bleach

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PRIORITY_FILE = os.getenv("PRIORITY_FILE", "data/senders_priority.csv")
CACHE_DIR = Path(os.getenv("CACHE_DIR", "data/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OUT_DIR = Path("data")
OUT_DIR.mkdir(parents=True, exist_ok=True)
MESSAGES_DIR = OUT_DIR / "messages"
MESSAGES_DIR.mkdir(parents=True, exist_ok=True)

DEBUG_INCLUDE_ALL = os.getenv("DEBUG_INCLUDE_ALL", "").lower() in ("1", "true", "yes")

# Sanitization settings
ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "img", "table", "tr", "td", "th", "thead", "tbody", "tfoot", "style",
    "p", "br", "h1", "h2", "h3", "strong", "b", "em", "i", "ul", "ol", "li", "blockquote"
}
ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "a": ["href", "title", "rel", "target"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto", "data"]

INDEX_TEMPLATE = '''
<!doctype html>
<html><head><meta charset="utf-8"><title>Newsletter Hell (debug)</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial;margin:0;padding:24px;background:#f6f7fb;color:#111}
.wrap{max-width:1100px;margin:0 auto}
.header{display:flex;justify-content:space-between;align-items:center}
.controls{font-size:0.95rem;color:#333}
.msg{background:#fff;padding:14px;border-radius:8px;margin-bottom:12px;border:1px solid #eaeef6}
.title{font-weight:700;cursor:pointer}
.detail-container{margin-top:8px}
.plain-paragraph{margin:10px 0;line-height:1.6;color:#222;white-space:pre-wrap}
.msg-html img{max-width:100%;height:auto}
.debug-pre{background:#fff;padding:10px;border-radius:8px;border:1px solid #ddd;white-space:pre-wrap;max-height:300px;overflow:auto}
</style></head><body>
<div class="wrap">
  <div class="header">
    <div>
      <h1>Newsletter Hell — debug</h1>
      <div>Období: {{ period_start }} — {{ period_end }}</div>
      <div>DEBUG_INCLUDE_ALL={{ debug_include_all }}</div>
    </div>
    <div class="controls">
      <label><input type="checkbox" class="prio-filter" data-prio="1" checked> P1</label>
      <label><input type="checkbox" class="prio-filter" data-prio="2" checked> P2</label>
      <label><input type="checkbox" class="prio-filter" data-prio="3" checked> P3</label>
    </div>
  </div>

  <details>
    <summary>Debug selection (reasons why candidates were included/skipped)</summary>
    <div class="debug-pre">{{ debug_selection_raw }}</div>
  </details>

  <div style="margin:12px 0"><strong>Generated messages: {{ messages|length }}</strong></div>

{% for m in messages %}
<article class="msg" id="m-{{ m.safe_id }}" data-uid="{{ m.safe_id }}" data-priority="{{ m._priority }}"
         data-plain='{{ m.plain_b64|safe }}' data-plain-render='{{ m.plain_render_b64|safe }}' data-plain-html='{{ m.plain_html_b64|safe }}'>
  <div>
    <div class="title" role="button" tabindex="0">{{ m.subject }}</div>
    <div style="font-size:0.9rem;color:#666">{{ m.from }} • {{ m.date }}</div>
    <div class="detail-container" data-loaded="false"></div>
  </div>
</article>
{% endfor %}

</div>

<script>
(function(){
  function log(){ if(console && console.log) console.log.apply(console, arguments); }
  function base64ToUtf8(b64){
    if(!b64) return null;
    if(b64.indexOf('&') !== -1){
      try { var ta=document.createElement('textarea'); ta.innerHTML=b64; b64=ta.value;} catch(e){}
    }
    try { var bin=atob(b64); } catch(e){ return null; }
    try {
      if(typeof TextDecoder !== 'undefined'){
        var arr=new Uint8Array(bin.length);
        for(var i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
        return new TextDecoder('utf-8').decode(arr);
      } else { return decodeURIComponent(escape(bin)); }
    } catch(e){ try{ return decodeURIComponent(escape(bin)); } catch(_) { return bin; } }
  }

  function escapeHtml(s){ if(!s) return ''; return s.replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];}); }

  function renderPlainForArticle(article){
    var container=article.querySelector('.detail-container'); if(!container) return;
    if(container.getAttribute('data-loaded')==='true'){ var d=container.querySelector('.plain-rendered'); if(d){ d.style.display=(d.style.display==='none'?'':'none'); } return; }

    var renderB64=article.getAttribute('data-plain-render')||'';
    var renderHtml=base64ToUtf8(renderB64);
    if(renderHtml){ var w=document.createElement('div'); w.className='plain-rendered msg-html'; w.innerHTML=renderHtml; container.appendChild(w); container.setAttribute('data-loaded','true'); log('rendered plain_render for', article.getAttribute('data-uid')); return; }

    var htmlB64=article.getAttribute('data-plain-html')||'';
    var htmlDecoded=base64ToUtf8(htmlB64);
    if(htmlDecoded){ var w2=document.createElement('div'); w2.className='plain-rendered msg-html'; w2.innerHTML=htmlDecoded; container.appendChild(w2); container.setAttribute('data-loaded','true'); log('rendered plain_html for', article.getAttribute('data-uid')); return; }

    var b64=article.getAttribute('data-plain')||'';
    var plain=base64ToUtf8(b64);
    if(plain){ var parts=plain.split(/\\n{2,}|\\r\\n{2,}/).map(function(p){return p.trim();}).filter(Boolean); var w3=document.createElement('div'); w3.className='plain-rendered'; w3.innerHTML=parts.map(function(p){ return '<p class="plain-paragraph">'+escapeHtml(p)+'</p>'; }).join(''); container.appendChild(w3); container.setAttribute('data-loaded','true'); log('rendered plain_text for', article.getAttribute('data-uid')); return; }

    var uid=article.getAttribute('data-uid'); if(!uid) return;
    var url='messages/'+uid+'.json'; log('fetch fallback JSON', url);
    fetch(url).then(function(resp){ if(!resp.ok) throw new Error('HTTP '+resp.status); return resp.json(); }).then(function(obj){
      if(obj.plain_render_html){ var w4=document.createElement('div'); w4.className='plain-rendered msg-html'; w4.innerHTML=obj.plain_render_html; container.appendChild(w4); }
      else if(obj.plain_html){ var w5=document.createElement('div'); w5.className='plain-rendered msg-html'; w5.innerHTML=obj.plain_html; container.appendChild(w5); }
      else { var text=obj.plain_text||obj.overview||''; var parts2=text.split(/\\n{2,}|\\r\\n{2,}/).map(function(p){return p.trim();}).filter(Boolean); var w6=document.createElement('div'); w6.className='plain-rendered'; w6.innerHTML=parts2.map(function(p){ return '<p class="plain-paragraph">'+escapeHtml(p)+'</p>'; }).join(''); container.appendChild(w6); }
      container.setAttribute('data-loaded','true');
    }).catch(function(err){ console.error('Fallback fetch failed', err); var w=document.createElement('div'); w.className='plain-rendered'; w.innerHTML='<p class="plain-paragraph">Nelze načíst obsah (fallback selhal).</p>'; container.appendChild(w); container.setAttribute('data-loaded','true'); });
  }

  function attachTitleHandlers(){
    if(!attachTitleHandlers._delegationAttached){
      document.addEventListener('click', function(e){ var t=e.target.closest && e.target.closest('.title[role="button"]'); if(t){ var art=t.closest('article.msg'); if(art) renderPlainForArticle(art); } });
      attachTitleHandlers._delegationAttached=true;
    }
    document.querySelectorAll('.title[role="button"]').forEach(function(el){ if(el._hasKey) return; el.addEventListener('keydown', function(ev){ if(ev.key==='Enter'||ev.key===' '){ ev.preventDefault(); var art=el.closest('article.msg'); if(art) renderPlainForArticle(art); } }); el._hasKey=true; });
  }

  function applyPriorityFilter(){
    var checked=Array.from(document.querySelectorAll('.prio-filter')).filter(cb=>cb.checked).map(cb=>cb.getAttribute('data-prio'));
    log('applyPriorityFilter: checked',checked);
    var cnt=0;
    document.querySelectorAll('article.msg').forEach(function(article){ var p=article.getAttribute('data-priority')||''; if(p && checked.indexOf(p)===-1){ article.style.display='none'; } else { article.style.display=''; cnt++; } });
    log('applyPriorityFilter: visible articles=',cnt);
  }

  function init(){ try{ attachTitleHandlers(); document.querySelectorAll('.prio-filter').forEach(function(cb){ cb.addEventListener('change', applyPriorityFilter); }); applyPriorityFilter(); } catch(e){ console.error('init error', e); } }
  if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', init); } else { init(); }

})();
</script>
</body></html>
'''

# ---- helper functions ----

TECHNICAL_PATTERNS = [
    r'(?i)nezobrazuje se vám newsletter správně',
    r'(?i)if you are having trouble viewing this email',
    r'(?i)click here to view in your browser',
    r'(?i)zobrazit v prohlížeči',
    r'(?i)if you can\\'t see images',
    r'(?i)view in browser',
    r'(?i)local tracking pixel',
]

URL_RE = re.compile(r'(https?://[^\\s\\'\"<>]+)', re.IGNORECASE)

def _strip_technical(text: str) -> str:
    t = text or ""
    for p in TECHNICAL_PATTERNS:
        t = re.sub(p, '', t)
    lines = [ln.strip() for ln in t.splitlines()]
    useful = []
    for ln in lines:
        if not ln: continue
        if len(ln) < 10: continue
        if re.search(r'(?i)(unsubscribe|odhlásit|preferences|manage your subscription|privacy policy|view in browser|zobrazit v prohlíči)', ln):
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

def format_plain_for_display(plain_text: str, width: int = 84) -> str:
    if not plain_text:
        return '<div class="msg-html"><p class="plain-paragraph">Žádné nové užitečné informace.</p></div>'
    parts = re.split(r'\n{2,}|\r\n{2,}', plain_text)
    out_parts = []
    for p in parts:
        p = p.strip()
        if not p: continue
        p = re.sub(r'\n+', ' ', p)
        p = re.sub(r'[ \t]{2,}', ' ', p)
        try:
            wrapped = textwrap.fill(p, width=width)
        except Exception:
            wrapped = p
        esc = wrapped.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&#39;')
        out_parts.append(f'<p class="plain-paragraph">{esc}</p>')
    return '<div class="msg-html">' + ''.join(out_parts) + '</div>'

def safe_id_for(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="ignore")).hexdigest()

def load_cache(uid: str) -> Optional[Dict[str, Any]]:
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
    if not priority_map and not DEBUG_INCLUDE_ALL:
        logger.error("Priority map not found or empty: %s", PRIORITY_FILE)
        return
    logger.info("Loaded %d priority entries (file: %s)", len(priority_map), PRIORITY_FILE)

    # build exact/domain maps
    exact_map: Dict[str,int] = {}
    domain_map: Dict[str,int] = {}
    for k,v in (priority_map or {}).items():
        kk = (k or "").strip().lower()
        try:
            pv = int(v)
        except Exception:
            continue
        if '@' in kk:
            exact_map[kk] = pv
        elif kk:
            domain_map[kk] = pv
    logger.info("Priority exact entries: %d, domain entries: %d", len(exact_map), len(domain_map))

    # window last 7 days
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    start_dt = now - timedelta(days=7)
    end_dt = now
    logger.info("Window: %s -> %s (UTC)", start_dt.isoformat(), end_dt.isoformat())

    msgs = fetch_messages_since(IMAP_HOST, IMAP_USER, IMAP_PASSWORD, start_dt, mailbox="INBOX")
    logger.info("IMAP candidates: %d", len(msgs))

    seen = set(); unique: List[Dict[str,Any]] = []
    for m in msgs:
        mid = (m.get("message_id") or "").strip()
        key = mid if mid else m.get("fallback_hash") or m.get("uid")
        if not key: continue
        if key in seen: continue
        seen.add(key); unique.append(m)
    logger.info("After dedupe: %d", len(unique))

    debug_selection = []
    selected: List[Dict[str,Any]] = []

    for m in unique:
        try:
            entry = {"subject": m.get("subject"), "from": m.get("from"), "uid": m.get("uid") or m.get("message_id")}
            if not m.get("is_newsletter"):
                entry["reason"]="not_newsletter"; debug_selection.append(entry); continue
            if subject_is_excluded(m.get("subject","")):
                entry["reason"]="subject_excluded"; debug_selection.append(entry); continue

            from_header = m.get("from","") or ""
            _, sender_email = parseaddr(from_header)
            sender_email = (sender_email or "").strip().lower()
            if not sender_email:
                entry["reason"]="no_sender_email"; debug_selection.append(entry); continue

            pr = None
            if DEBUG_INCLUDE_ALL:
                pr = 3
                entry["matched"]="debug_include_all"
            else:
                if sender_email in exact_map:
                    pr = exact_map[sender_email]; entry["matched"]="exact"
                else:
                    try:
                        domain = sender_email.split('@',1)[1]
                    except Exception:
                        domain = ""
                    if domain and domain in domain_map:
                        pr = domain_map[domain]; entry["matched"]="domain"

            if pr is None:
                entry["reason"]="not_in_priority_map"; debug_selection.append(entry); continue

            m["_priority"] = int(pr)
            entry["priority"]=m["_priority"]

            raw_html = m.get("html","") or ""
            m["raw_html"]=raw_html
            m["html"]=sanitize_html(raw_html)

            dt_val = m.get("date") or m.get("internal_date") or None
            ts = parse_date_to_ts(dt_val)
            if ts == 0:
                ts = int(datetime.utcnow().replace(tzinfo=timezone.utc).timestamp())
            m["_date_ts"]=ts
            try:
                if isinstance(dt_val, datetime):
                    m["date"]=dt_val.astimezone(timezone.utc).isoformat()
                elif isinstance(dt_val, str):
                    m["date"]=dt_val
                else:
                    m["date"]=datetime.utcfromtimestamp(ts).replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                m["date"]=str(dt_val or "")

            selected.append(m)
            entry["included"]=True
            debug_selection.append(entry)
        except Exception:
            logger.exception("Skipping message during selection: %s", m.get("subject"))

    # write debug selection
    try:
        (OUT_DIR / "debug_selection.json").write_text(json.dumps(debug_selection, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Wrote debug_selection.json with %d entries", len(debug_selection))
    except Exception:
        logger.exception("Failed to write debug_selection.json")

    logger.info("Selected by priority & newsletter filter: %d", len(selected))

    # sort by priority asc then newest first
    selected_sorted = sorted(selected, key=lambda x: (x.get("_priority",999), -int(x.get("_date_ts",0))))

    for m in selected_sorted:
        raw_id = (m.get("message_id") or m.get("fallback_hash") or m.get("uid") or "")
        safe_id = safe_id_for(raw_id)
        m["safe_id"]=safe_id

        cached = load_cache(safe_id)
        if cached is not None:
            summary_obj = cached
        else:
            try:
                summary_obj = extract_items_from_message(m.get("subject",""), m.get("from",""), m.get("text",""), m.get("html",""), safe_id)
                items = [it for it in summary_obj.get("items", []) if not re.search(r"(?i)view in browser|unsubscribe|manage your subscription|preferences", (it.get("full_text") or "") + " " + (it.get("summary") or ""))]
                summary_obj["items"]=items
            except Exception as e:
                logger.exception("Summarize failed uid=%s: %s", safe_id, e)
                summary_obj={"overview":"","items":[]}
            save_cache(safe_id, summary_obj)

        m["overview"]=summary_obj.get("overview") or ""
        m["_items"]=summary_obj.get("items") or []

        raw_html = m.get("raw_html") or ""
        plain = html_to_plain_text(raw_html or m.get("text","") or "")
        try:
            b64 = base64.b64encode(plain.encode("utf-8")).decode("ascii")
        except Exception:
            b64 = ""
        m["plain_b64"]=b64

        # plain_render_html (formatted plain text)
        try:
            render_html = format_plain_for_display(plain)
            render_b64 = base64.b64encode(render_html.encode("utf-8")).decode("ascii")
        except Exception:
            render_html = ""
            render_b64 = ""
        m["plain_render_html"]=render_html
        m["plain_render_b64"]=render_b64

        # sanitized HTML fallback
        try:
            sanitized_html = sanitize_html(raw_html or "")
            sanitized_html_wrapped = f'<div class="msg-html">{sanitized_html}</div>'
            html_b64 = base64.b64encode(sanitized_html_wrapped.encode("utf-8")).decode("ascii")
        except Exception:
            sanitized_html_wrapped = ""
            html_b64 = ""
        m["plain_html"]=sanitized_html_wrapped
        m["plain_html_b64"]=html_b64

        # write per-message JSON
        j = {
            "subject": m.get("subject"),
            "from": m.get("from"),
            "date": m.get("date"),
            "priority": m.get("_priority"),
            "items": m["_items"],
            "overview": m["overview"],
            "plain_text": plain,
            "plain_html": sanitized_html_wrapped,
            "plain_render_html": render_html
        }
        (MESSAGES_DIR / f"{safe_id}.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")

        # per-message html backup
        if raw_html.strip():
            try:
                msg_html = "<!doctype html><html><head><meta charset='utf-8'><title>{}</title></head><body>{}</body></html>".format(
                    (m.get("subject") or "").replace("</","</"), raw_html
                )
            except Exception:
                msg_html = "<!doctype html><html><head><meta charset='utf-8'><title>{}</title></head><body><pre>{}</pre></body></html>".format(
                    (m.get("subject") or ""), (m.get("text") or "")
                )
        else:
            msg_html = "<!doctype html><html><head><meta charset='utf-8'><title>{}</title></head><body><h1>{}</h1><pre style='white-space:pre-wrap;'>{}</pre></body></html>".format(
                (m.get("subject") or ""), (m.get("subject") or ""), (m.get("text") or "")
            )
        (MESSAGES_DIR / f"{safe_id}.html").write_text(msg_html, encoding="utf-8")

    # render index
    period_start = start_dt.strftime("%d/%m/%Y")
    period_end = end_dt.strftime("%d/%m/%Y")
    index_t = Template(INDEX_TEMPLATE)
    html = index_t.render(messages=selected_sorted, period_start=period_start, period_end=period_end, debug_selection_raw=json.dumps(debug_selection, ensure_ascii=False, indent=2), debug_include_all=str(DEBUG_INCLUDE_ALL))
    (OUT_DIR / "test_digest.html").write_text(html, encoding="utf-8")
    logger.info("Generated %d messages. Digest saved to data/test_digest.html", len(selected_sorted))

if __name__ == "__main__":
    main()
