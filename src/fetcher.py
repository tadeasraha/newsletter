import requests
from readability import Document
from bs4 import BeautifulSoup

def extract_text_from_html(html):
    doc = Document(html)
    content = doc.summary()
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(separator="\n").strip()
    return text

def fetch_url(url, timeout=15):
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "newsletter-aggregator/1.0"})
        if resp.status_code == 200 and 'text/html' in resp.headers.get('Content-Type',''):
            title_tag = BeautifulSoup(resp.text, "html.parser").title
            title_text = title_tag.get_text().strip() if title_tag else ""
            text = extract_text_from_html(resp.text)
            summary = "\n\n".join(text.split("\n\n")[:2])
            return {"url": url, "title": title_text, "summary": summary}
    except Exception:
        return None
    return None
