"""
Modul pro načítání zpráv z IMAP serveru.
Po zpracování zprávu označí jako přečtenou a přesune do archivní složky.
"""
from imapclient import IMAPClient
from typing import List, Dict, Any
import email
from email.header import decode_header
import re


def decode_header_value(header_value: str) -> str:
    """Dekóduje header hodnotu z MIME formátu."""
    if not header_value:
        return ""
    
    decoded_parts = decode_header(header_value)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(encoding or 'utf-8', errors='ignore'))
            except:
                result.append(part.decode('utf-8', errors='ignore'))
        else:
            result.append(str(part))
    return ''.join(result)


def fetch_new_messages(server: str, port: int, user: str, password: str, 
                       sources: List[Dict[str, Any]], processed_ids: set,
                       archive_mailbox: str) -> List[Dict[str, Any]]:
    """
    Načte nové zprávy z IMAP serveru podle konfigurace zdrojů.
    Po zpracování zprávu označí jako přečtenou a přesune do archivní složky.
    
    Args:
        server: IMAP server
        port: IMAP port
        user: IMAP uživatel
        password: IMAP heslo
        sources: Seznam zdrojů z config/sources.yaml
        processed_ids: Množina již zpracovaných message_id
        archive_mailbox: Název složky pro archivaci zpracovaných zpráv
        
    Returns:
        Seznam nových zpráv s metadaty
    """
    messages = []
    
    try:
        with IMAPClient(server, port=port, ssl=True) as client:
            client.login(user, password)
            print(f"Připojeno k IMAP serveru {server}")
            
            # Vytvoření archivní složky, pokud neexistuje
            try:
                if not client.folder_exists(archive_mailbox):
                    client.create_folder(archive_mailbox)
                    print(f"Vytvořena archivní složka: {archive_mailbox}")
            except Exception as e:
                print(f"Varování: Nelze vytvořit archivní složku: {e}")
            
            # Procházení zdrojů
            for source in sources:
                if not source.get('enabled', True):
                    continue
                
                folder = source.get('folder', 'INBOX')
                from_pattern = source.get('from_pattern', '').lower()
                
                try:
                    client.select_folder(folder, readonly=False)
                    print(f"Procházím složku: {folder} pro zdroj: {source['name']}")
                    
                    # Hledat nepřečtené zprávy
                    message_ids = client.search(['UNSEEN'])
                    print(f"Nalezeno {len(message_ids)} nepřečtených zpráv")
                    
                    if not message_ids:
                        continue
                    
                    # Načíst zprávy
                    raw_messages = client.fetch(message_ids, ['RFC822', 'FLAGS'])
                    
                    for msg_id, data in raw_messages.items():
                        try:
                            email_message = email.message_from_bytes(data[b'RFC822'])
                            
                            # Získat From adresu
                            from_addr = decode_header_value(email_message.get('From', ''))
                            message_id = email_message.get('Message-ID', f'<{msg_id}>')
                            
                            # Kontrola, zda zpráva odpovídá vzoru a není již zpracována
                            if from_pattern and from_pattern not in from_addr.lower():
                                continue
                            
                            if message_id in processed_ids:
                                continue
                            
                            # Získat subject a body
                            subject = decode_header_value(email_message.get('Subject', 'Bez předmětu'))
                            
                            # Extrahovat text a HTML obsah
                            body_text = ""
                            body_html = ""
                            
                            if email_message.is_multipart():
                                for part in email_message.walk():
                                    content_type = part.get_content_type()
                                    if content_type == 'text/plain':
                                        try:
                                            body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        except:
                                            pass
                                    elif content_type == 'text/html':
                                        try:
                                            body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        except:
                                            pass
                            else:
                                try:
                                    payload = email_message.get_payload(decode=True)
                                    if payload:
                                        body_text = payload.decode('utf-8', errors='ignore')
                                except:
                                    pass
                            
                            messages.append({
                                'message_id': message_id,
                                'uid': msg_id,
                                'from': from_addr,
                                'subject': subject,
                                'body_text': body_text,
                                'body_html': body_html,
                                'source': source,
                                'folder': folder
                            })
                            
                            # Označit jako přečtenou a přesunout do archivu
                            try:
                                # Označit jako přečtenou
                                client.add_flags(msg_id, ['\\Seen'])
                                print(f"Zpráva {msg_id} označena jako přečtená")
                                
                                # Pokusit se přesunout zprávu
                                try:
                                    client.move(msg_id, archive_mailbox)
                                    print(f"Zpráva {msg_id} přesunuta do {archive_mailbox}")
                                except Exception as move_error:
                                    # Fallback: copy + delete + expunge
                                    print(f"MOVE selhalo, použit fallback: {move_error}")
                                    client.copy(msg_id, archive_mailbox)
                                    client.add_flags(msg_id, ['\\Deleted'])
                                    client.expunge()
                                    print(f"Zpráva {msg_id} zkopírována a smazána (fallback)")
                            except Exception as e:
                                print(f"Varování: Nelze archivovat zprávu {msg_id}: {e}")
                                
                        except Exception as e:
                            print(f"Chyba při zpracování zprávy {msg_id}: {e}")
                            continue
                    
                except Exception as e:
                    print(f"Chyba při procházení složky {folder}: {e}")
                    continue
            
    except Exception as e:
        print(f"Chyba při připojení k IMAP: {e}")
        raise
    
    return messages


def extract_first_link(text: str, html: str) -> str:
    """
    Extrahuje první HTTP(S) odkaz ze zprávy.
    
    Args:
        text: Textová verze zprávy
        html: HTML verze zprávy
        
    Returns:
        První nalezený odkaz nebo prázdný řetězec
    """
    # Hledat v HTML pomocí regex
    if html:
        html_links = re.findall(r'href=["\']?(https?://[^"\'>\s]+)', html)
        if html_links:
            return html_links[0]
    
    # Hledat v textu
    if text:
        text_links = re.findall(r'https?://[^\s]+', text)
        if text_links:
            return text_links[0]
    
    return ""
