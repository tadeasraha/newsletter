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

ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {"img"}
ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "a": ["href", "title", "rel", "target"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

# index template — now includes only snippet (short summary) and lazy load button
INDEX_TEMPLATE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Týdenní digest</title>
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
      .title { font-weight:700; }
    </style>
  </head>
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
          <div>
            <a href="messages/{{ m.uid }}.html" target="_blank">Otevřít celý e‑mail</a>
          </div>
        </div>

        <div class="snippet">{{ m.snippet }}</div>

        <div class="detail-container" data-loaded="false">
          <button class="load-detail">Načíst rozšířené shrnutí</button>
        </div>
      </article>
      {% endfor %}
    </div>

<script>
(async function(){
  document.querySelectorAll('.load-detail').forEach(btn=>{
    btn.addEventListener('click', async (e)=>{
      const container = btn.closest('.detail-container');
      const article = btn.closest('article.msg');
      const uid = article.getAttribute('data-uid');
      if(container.getAttribute('data-loaded') === 'true') {
        // toggle display
        const details = container.querySelector('.details-rendered');
        if(details) details.style.display = details.style.display === 'none' ? '' : 'none';
        return;
      }
      btn.disabled = true;
      btn.textContent = 'Načítám…';
      try {
        const resp = await fetch(`messages/${uid}.json`);
        if(!resp.ok) throw new Error('Chyba při načítání detailu');
        const data = await resp.json();
        // render structured items: two-column list (title left bold, summary right) each expandable to full_text
        const wrapper = document.createElement('div');
        wrapper.className = 'details-rendered';
        data.items.forEach((it, idx)=>{
          const sec = document.createElement('details');
          const summ = document.createElement('summary');
          summ.innerHTML = `<strong>${escapeHtml(it.title)}</strong> — <span style="color:#444">${escapeHtml(it.summary)}</span>`;
          sec.appendChild(summ);

          const content = document.createElement('div');
          content.style.padding = '8px 0';
          // left-right layout
          const table = document.createElement('div');
          table.style.display = 'grid';
          table.style.gridTemplateColumns = '1fr 2fr';
          table.style.gap = '12px';
          const left = document.createElement('div');
          left.innerHTML = `<strong>${escapeHtml(it.title)}</strong>`;
          const right = document.createElement('div');
          right.innerHTML = `<div style="color:#333">${escapeHtml(it.summary)}</div><div style="margin-top:8px"><a href="#" class="show-full" data-idx="${idx}">Zobrazit celý text</a></div>`;
          table.appendChild(left);
          table.appendChild(right);
          content.appendChild(table);

          // full text hidden
          const full = document.createElement('div');
          full.className = 'full-text hidden';
          full.style.marginTop = '8px';
          full.style.borderTop = '1px solid #eee';
          full.style.paddingTop = '8px';
          full.innerHTML = renderFullTextHtml(it.full_text, it.link);
          content.appendChild(full);

          sec.appendChild(content);
          wrapper.appendChild(sec);

          // event for show-full link
          right.querySelector('.show-full').addEventListener('click', (ev)=>{
            ev.preventDefault();
            full.classList.toggle('hidden');
          });
        });

        container.appendChild(wrapper);
        container.setAttribute('data-loaded','true');
        btn.textContent = 'Skrýt / zobrazit shrnutí';
      } catch (err) {
        console.error(err);
        btn.textContent = 'Chyba při načtení';
      } finally {
        btn.disabled = false;
      }
    });
  });

  function escapeHtml(s) {
    if(!s) return '';
    return s.replace(/[&<>"']/g, function(m){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]; });
  }

  function renderFullTextHtml(full_text, link) {
    let out = '';
    // preserve simple links
    if(link) {
      out += `<p><a href="${escapeHtml(link)}" target="_blank">${escapeHtml(link)}</a></p>`;
    }
    out += '<pre style="white-space:pre-wrap;">' + escapeHtml(full_text || '') + '</pre>';
    return out;
  }
})();
</script>
  </body>
</html>
