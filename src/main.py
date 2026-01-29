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
    "img", "table", "tr", "td", "th", "thead", "tbody", "
