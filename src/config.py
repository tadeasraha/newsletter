import os

IMAP_HOST = os.getenv("IMAP_HOST")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

OPENAI_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API")

# Limits / defaults
FETCH_TIMEOUT = 15
PARALLEL_FETCH = 6
DEFAULT_PRIORITY = 3  # pokud chybí, použije se 3
DIGEST_RECIPIENT = IMAP_USER  # pošli digest na vlastní adresu (raha@volny.cz)
