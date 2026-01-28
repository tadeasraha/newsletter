"""
Konfigurační modul pro newsletter agregátor.
Načítá proměnné prostředí a poskytuje výchozí hodnoty.
"""
import os
from dotenv import load_dotenv

# Načíst .env soubor, pokud existuje
load_dotenv()

# IMAP konfigurace
IMAP_SERVER = os.getenv("IMAP_SERVER", "")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")

# SMTP konfigurace
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# OpenAI konfigurace (volitelné)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Výchozí priorita pro newslettery
DEFAULT_PRIORITY = 3

# Příjemce digestu (výchozí je IMAP uživatel)
DIGEST_RECIPIENT = os.getenv("DIGEST_RECIPIENT", IMAP_USER)

# Archivní složka pro zpracované zprávy
ARCHIVE_MAILBOX = "Newsletter 2"

# Git konfigurace pro commity
COMMIT_USER_NAME = os.getenv("COMMIT_USER_NAME", "Newsletter Bot")
COMMIT_USER_EMAIL = os.getenv("COMMIT_USER_EMAIL", "bot@newsletter.local")
