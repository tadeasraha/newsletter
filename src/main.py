#!/usr/bin/env python3
"""
Debug-capable src/main.py

Features added for debugging:
- DEBUG_INCLUDE_ALL (env var) -> if set to "1"/"true", include ALL IMAP candidates (bypass priority filter).
- Writes data/debug_selection.json and embeds its contents into generated HTML inside a <details> block.
- Additional console.log in client JS to show filter/render behavior.
- Otherwise preserves strict priority filtering and safe sanitization.
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

DEBUG_INCLUDE_ALL = os.getenv("DEBUG_INCLUDE_ALL", "").lower() in ("1","true","yes")

# HTML sanitization settings
ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "img","table","tr","td","th","thead","tbody","tfoot","style",
    "p","br","h1","h2","h3","strong","b","em","i","ul","ol","li","blockquote"
}
ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "img":["src","alt","title","width","height","loading"],
    "a":["href","title","rel","target"],
    "td":["colspan","rowspan"],
    "th":["colspan","rowspan"],
}
ALLOWED_PROTOCOLS = ["http","https","mailto","data"]

INDEX_TEMPLATE = """<!doctype html>
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
    if(b64.indexOf('&') !== -1){ try{ var ta=document.createElement('textarea'); ta.innerHTML=b64; b64=ta.value;}catch(e){} }
    try { var bin=atob(b64); } catch(e){ return null; }
    try {
      if(typeof TextDecoder !== 'undefined'){
        var arr=new Uint8Array(bin.length);
        for(var i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
        return new TextDecoder('utf-8').decode(arr);
      } else { return decodeURIComponent(escape(bin)); }
    } catch(e){ try{ return decodeURIComponent(escape(bin)); }catch(_){ return bin; } }
  }

  function escapeHtml(s){ if(!s) return ''; return s.replace(/[&<>"']/g, function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];}); }

  function renderPlainForArticle(article){
    var container=article.querySelector('.detail-container'); if(!container) return;
    if(container.getAttribute('data-loaded')==='true'){ var d=container.querySelector('.plain-rendered'); if(d){ d.style.display=(d.style.display==='none' ? '' : 'none'); } return; }

    var renderB64=article.getAttribute('data-plain-render')||'';
    var renderHtml=base64ToUtf8(renderB64);
    if(renderHtml){ var w=document.createElement('div'); w.className='plain-rendered msg-html'; w.innerHTML=renderHtml; container.appendChild(w); container.setAttribute('data-loaded','true'); log('rendered plain_render for', article.getAttribute('data-uid')); return; }

    var htmlB64=article.getAttribute('data-plain-html')||'';
    var htmlDecoded=base64ToUtf8(htmlB64);
    if(htmlDecoded){ var w2=document.createElement('div'); w2.className='plain-rendered msg-html'; w2.innerHTML=htmlDecoded; container.appendChild(w2); container.setAttribute('data-loaded','true'); log('rendered plain_html for', article.getAttribute('data-uid')); return; }

    var b64=article.getAttribute('data-plain')||'';
    var plain=base64ToUtf8(b64);
    if(plain){ var parts=plain.split(/\n{2,}|\r\n{2,}/).map(function(p){return p.trim();}).filter(Boolean); var w3=document.createElement('div'); w3.className='plain-rendered'; w3.innerHTML=parts.map(function(p){ return '<p class="plain-paragraph">'+escapeHtml(p)+'</p>'; }).join(''); container.appendChild(w3); container.setAttribute('data-loaded','true'); log('rendered plain_text for', article.getAttribute('data-uid')); return; }

    var uid=article.getAttribute('data-uid'); if(!uid) return;
    var url='messages/'+uid+'.json'; log('fetch fallback JSON', url);
    fetch(url).then(function(resp){ if(!resp.ok) throw new Error('HTTP '+resp.status); return resp.json(); }).then(function(obj){
      if(obj.plain_render_html){ var w4=document.createElement('div'); w4.className='plain-rendered msg-html'; w4.innerHTML=obj.plain_render_html; container.appendChild(w4); }
      else if(obj.plain_html){ var w5=document.createElement('div'); w5.className='plain-rendered msg-html'; w5.innerHTML=obj.plain_html; container.appendChild(w5); }
      else { var text=obj.plain_text||obj.overview||''; var parts=text.split(/\n{2,}|\r\n{2,}/).map(function(p){return p.trim();}).filter(Boolean); var w6=document.createElement('div'); w6.className='plain-rendered'; w6.innerHTML=parts.map(function(p){ return '<p class="plain-paragraph">'+escapeHtml(p)+'</p>'; }).join(''); container.appendChild(w6); }
      container.setAttribute('data-loaded','true');
    }).catch(function(err){ console.error('Fallback fetch failed', err); var w=document.createElement('div'); w.className='plain-rendered'; w.innerHTML='<p class="plain-paragraph">Nelze načíst obsah (fallback selhal).</p>'; container.appendChild(w); container.setAttribute('data-loaded','true'); });
  }

  function attachTitleHandlers(){
    if(!attachTitleHandlers._delegationAttached){
      document.addEventListener('click', function(e){ var t=e.target.closest && e.target.closest('.title[role="button"]'); if(t){ var art=t.closest('article.msg'); if(art) renderPlainForArticle(art); } });
      attachTitleHandlers._delegationAttached=true;
    }
    document.querySelectorAll('.title[role="button"]').forEach(function(el){ if(el._hasKey) return; el.addEventListener('keydown', function(ev){ if(ev.key==='Enter' || ev.key===' '){ ev.preventDefault(); var art=el.closest('article.msg'); if(art) renderPlainForArticle(art); } }); el._hasKey=true; });
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
