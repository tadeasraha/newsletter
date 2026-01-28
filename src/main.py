"""
Hlavní orchestrační modul pro newsletter agregátor.
"""
import yaml
from typing import List, Dict, Any

from src import config
from src.state import load_state, save_state
from src.imap_ingest import fetch_new_messages, extract_first_link
from src.fetcher import fetch_article
from src.generator import generate_digest_html
from src.send import send_email
from src.ai_reprio import reprioritize


def load_sources() -> List[Dict[str, Any]]:
    """Načte konfiguraci zdrojů ze souboru sources.yaml."""
    try:
        with open('config/sources.yaml', 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data.get('sources', [])
    except Exception as e:
        print(f"Chyba při načítání sources.yaml: {e}")
        return []


def main():
    """Hlavní funkce aplikace."""
    print("=== Newsletter Agregátor ===")
    print("Načítání konfigurace...")
    
    # Načíst zdroje
    sources = load_sources()
    if not sources:
        print("Žádné zdroje nenalezeny v config/sources.yaml")
        return
    
    print(f"Načteno {len(sources)} zdrojů")
    
    # Načíst stav
    state = load_state()
    processed_ids = state['processed_messages']
    print(f"Již zpracováno {len(processed_ids)} zpráv")
    
    # Načíst nové zprávy z IMAP
    print("\nNačítání nových zpráv z IMAP...")
    try:
        messages = fetch_new_messages(
            config.IMAP_SERVER,
            config.IMAP_PORT,
            config.IMAP_USER,
            config.IMAP_PASSWORD,
            sources,
            processed_ids,
            config.ARCHIVE_MAILBOX
        )
    except Exception as e:
        print(f"Chyba při načítání zpráv: {e}")
        return
    
    print(f"Nalezeno {len(messages)} nových zpráv")
    
    if not messages:
        print("Žádné nové zprávy k zpracování")
        return
    
    # Zpracovat zprávy a vytvořit položky digestu
    print("\nZpracování zpráv...")
    items = []
    
    for msg in messages:
        print(f"Zpracování: {msg['subject']}")
        
        # Extrahovat první odkaz
        link = extract_first_link(msg['body_text'], msg['body_html'])
        
        # Pokud je odkaz, pokusit se načíst obsah článku
        title = msg['subject']
        summary = ""
        
        if link:
            print(f"  Načítání článku: {link}")
            article = fetch_article(link)
            if article['title'] and article['title'] != 'Nepodařilo se načíst':
                title = article['title']
            summary = article['summary']
        
        # Pokud není summary z článku, použít začátek textu z e-mailu
        if not summary:
            body = msg['body_text'] or msg['body_html']
            if body:
                summary = body[:300] + '...' if len(body) > 300 else body
        
        item = {
            'message_id': msg['message_id'],
            'priority': msg['source'].get('priority', config.DEFAULT_PRIORITY),
            'title': title,
            'summary': summary,
            'link': link,
            'source_name': msg['source'].get('name', 'Unknown'),
            'ai_score': None
        }
        
        items.append(item)
        
        # Přidat do zpracovaných
        processed_ids.add(msg['message_id'])
    
    # AI re-prioritizace (pokud je k dispozici API klíč)
    ai_enabled = False
    if config.OPENAI_API_KEY:
        print("\nSpouštím AI re-prioritizaci...")
        ai_scores = reprioritize(items, config.OPENAI_API_KEY)
        
        if ai_scores:
            ai_enabled = True
            for item in items:
                if item['message_id'] in ai_scores:
                    item['ai_score'] = ai_scores[item['message_id']]
    
    # Vypočítat finální skóre a seřadit
    print("\nŘazení položek...")
    for item in items:
        # Vyšší priorita (1) je důležitější než nižší (3)
        # Převést na opačné skóre: priorita 1 -> 30, priorita 2 -> 20, priorita 3 -> 10
        priority_score = (4 - item['priority']) * 10
        
        # Přidat AI skóre (0-10)
        ai_component = int(item['ai_score'] * 10) if item['ai_score'] is not None else 0
        
        item['final_score'] = priority_score + ai_component
    
    # Seřadit podle final_score (sestupně)
    items.sort(key=lambda x: x['final_score'], reverse=True)
    
    # Vygenerovat HTML digest
    print("\nGenerování HTML digestu...")
    html = generate_digest_html(items, ai_enabled=ai_enabled)
    
    # Odeslat e-mail
    print("\nOdesílání e-mailu...")
    subject = f"📬 Newsletter Digest - {len(items)} nových položek"
    
    success = send_email(
        config.SMTP_SERVER,
        config.SMTP_PORT,
        config.SMTP_USER,
        config.SMTP_PASSWORD,
        config.DIGEST_RECIPIENT,
        subject,
        html,
        from_name="Newsletter Aggregator"
    )
    
    if not success:
        print("Chyba při odesílání e-mailu")
        return
    
    # Uložit stav
    print("\nUkládání stavu...")
    state['processed_messages'] = processed_ids
    save_state(state)
    
    print(f"\n✅ Hotovo! Zpracováno {len(items)} zpráv, digest odeslán na {config.DIGEST_RECIPIENT}")


if __name__ == '__main__':
    main()
