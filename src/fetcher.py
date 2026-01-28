"""
Modul pro načítání obsahu webových stránek.
Používá readability-lxml pro extrakci hlavního obsahu.
"""
import requests
from readability import Document
from bs4 import BeautifulSoup


def fetch_article(url: str, timeout: int = 10) -> dict:
    """
    Načte článek z URL a extrahuje jeho obsah.
    
    Args:
        url: URL článku
        timeout: Timeout pro HTTP požadavek v sekundách
        
    Returns:
        Slovník s klíči 'title' a 'summary'
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        # Použít readability pro extrakci obsahu
        doc = Document(response.text)
        title = doc.title()
        html_content = doc.summary()
        
        # Použít BeautifulSoup pro extrakci textu
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        
        # Zkrátit text na rozumnou délku pro summary
        summary = text[:500] + '...' if len(text) > 500 else text
        
        return {
            'title': title,
            'summary': summary
        }
    except Exception as e:
        print(f"Chyba při načítání článku z {url}: {e}")
        return {
            'title': 'Nepodařilo se načíst',
            'summary': f'Chyba: {str(e)}'
        }
