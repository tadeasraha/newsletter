#!/usr/bin/env python3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def save_digest_html(html: str, out_path: str = "data/test_digest.html") -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    logger.info("Saved digest to %s", str(p))
    return str(p)

def send_digest(html: str, dry_run: bool = True, out_path: str = "data/test_digest.html"):
    """
    Pokud dry_run=True, uloží HTML do souboru (není odesíláno).
    Pokud dry_run=False, implementujte zde SMTP odesílání (nebo jinak).
    """
    if dry_run:
        saved = save_digest_html(html, out_path=out_path)
        print(f"[DRY RUN] digest saved to {saved}")
        return saved
    else:
        # Tady můžeš přidat skutečné odesílání přes smtplib,
        # načtení SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD z env.
        raise NotImplementedError("Real send not implemented in stub")
