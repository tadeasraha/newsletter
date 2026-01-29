#!/usr/bin/env python3
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
.snippet{display:none}
.detail-container{margin-top:8px}
button{background:#1a73e8;color:#fff;padding:6px 10px;border-radius:8px;border:none;cursor:pointer}
.title{font-weight:700;font-size:1.05rem}
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
        <div class="title">{{ m.subject }}</div>
        {% if m._priority %}
          <span class="prio-square prio-{{ m._priority }}" title="Priority P{{ m._priority }}"></span>
        {% endif %}
      </div>
      <div class="meta">{{ m.from }} • {{ m.date }}</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
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
  function escapeHtml(s){ if(!s) return ''; return s.replace(/[&<>"']/g, function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];}); }

  // Rozbalit: dekóduj base64 uložený v data-plain a vykresli jako plain text
  document.querySelectorAll('.load-detail').forEach(function(btn){
    btn.addEventListener('click', function(ev){
      var container = btn.closest('.detail-container');
      var article = btn.closest('article.msg');
      var uid = article && article.getAttribute('data-uid');
      if(!uid) return;
      // toggle if already loaded
      if(container.getAttribute('data-loaded') === 'true'){
        var details = container.querySelector('.plain-rendered');
        if(details){
          var isHidden = details.style.display === 'none';
          details.style.display = isHidden ? '' : 'none';
          btn.textContent = isHidden ? 'Sbalit' : 'Rozbalit';
        }
        return;
      }
      btn.disabled = true;
      btn.textContent = 'Načítám…';
      try {
        var b64 = article.getAttribute('data-plain') || '';
        var plain = '';
        if(b64){
          try { plain = decodeURIComponent(escape(window.atob(b64))); } catch(e){ plain = window.atob(b64); }
        }
        if(!plain) plain = 'Žádný text k zobrazení.';
        // create paragraphs
        var parts = plain.split(/\n{2,}|\r\n{2,}/).map(function(p){ return p.trim(); }).filter(Boolean);
        var wrapper = document.createElement('div'); wrapper.className = 'plain-rendered';
        if(parts.length === 0){
          wrapper.innerHTML = '<p class="plain-paragraph">Žádné nové užitečné informace.</p>';
        } else {
          wrapper.innerHTML = parts.map(function(p){ return '<p class="plain-paragraph">' + escapeHtml(p) + '</p>'; }).join('');
        }
        container.appendChild(wrapper);
        container.setAttribute('data-loaded','true');
        btn.textContent = 'Sbalit';
      } catch(e){
        console.error(e);
        btn.textContent = 'Chyba';
      } finally {
        btn.disabled = false;
      }
    });
  });

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
  document.querySelectorAll('.prio-filter').forEach(function(cb){
    cb.addEventListener('change', applyPriorityFilter);
  });
  applyPriorityFilter();

})();
</script>
</body></html>
"""

Co udělat teď (rychle)
1) Vlož soubor výše přes GitHub web UI do src/main.py (Edit this file → vymaž → vlož → Commit directly to main).  
2) Spusť workflow (Actions → Weekly digest → Run) nebo lokálně:
   - export IMAP_HOST=... IMAP_USER=... IMAP_PASSWORD=...
   - python -m src.main
3) Pokud se objeví další chyba v logu, zkopíruj první 20–40 řádků stack trace sem a já to hned opravím.

Krátké vysvětlení
- Opravil jsem chybnou definici `ALLOWED_TAGS` (rozbitý řetězec) a ověřil syntaxi souboru. Pokud by se po commitu objevily jiné chyby (např. Jinja escaping u atributu `data-plain`), dám ti okamžitý malý patch — ale nejdřív nech to projít Pythonem.

Pokud chceš, připravím ještě drobnou bezpečnostní úpravu: při renderu Jinja může být base64 v atributu automaticky HTML‑escaped — pokud po commitu „Rozbalit“ stále nic dělat nebude, pošli výstup z DevTools podle kroků, které jsem popisoval dříve, a já doplním přesný fix (1–2 řádky).
