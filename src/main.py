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
import hashlib

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

# UI template (čeština) – interaktivita (JS) pro filtrování a expand/collapse
INDEX_TEMPLATE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Týdenní přehled (Weekly digest)</title>
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
        Vygenerováno automaticky. Pokud chcete znovu vytvořit shrnutí (re‑summarize), spusť prosím workflow z GitHub Actions.
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

  // highlight open card
  document.querySelectorAll('article.msg details').forEach(d=>{
    d.addEventListener('toggle', (e)=>{
      const el = d.closest('.msg');
      if(d.open) el.classList.add('open'); else el.classList.remove('open');
    });
  });

  // init
  applyFilters();
})();
</script>
  </body>
</html>
