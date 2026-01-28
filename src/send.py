"""
Modul pro odesílání e-mailů přes SMTP.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional


def send_email(server: str, port: int, user: str, password: str,
               recipient: str, subject: str, html_content: str,
               from_name: Optional[str] = None) -> bool:
    """
    Odešle e-mail s HTML obsahem přes SMTP.
    
    Args:
        server: SMTP server
        port: SMTP port
        user: SMTP uživatel
        password: SMTP heslo
        recipient: Příjemce e-mailu
        subject: Předmět e-mailu
        html_content: HTML obsah e-mailu
        from_name: Volitelné jméno odesílatele
        
    Returns:
        True pokud bylo odesílání úspěšné, jinak False
    """
    try:
        # Vytvořit zprávu
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = f"{from_name} <{user}>" if from_name else user
        message['To'] = recipient
        
        # Přidat HTML obsah
        html_part = MIMEText(html_content, 'html', 'utf-8')
        message.attach(html_part)
        
        # Připojit k SMTP serveru a odeslat
        with smtplib.SMTP(server, port) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(message)
        
        print(f"E-mail úspěšně odeslán na {recipient}")
        return True
        
    except Exception as e:
        print(f"Chyba při odesílání e-mailu: {e}")
        return False
