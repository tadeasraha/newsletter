import re
from html import escape
from bs4 import BeautifulSoup

# Seznam „technických/marketingových“ frází, které chceme odstranit (rozšiř podle potřeby)
TECHNICAL_PHRASES = [
    r'Nezobrazuje se vám newsletter správně',
    r'If you are having trouble viewing this email',
    r'Click here to view in your browser',
    r'Zobrazit v prohlížeči',
    r'If you can\'t see images',
    # přidej další fráze/regulární výrazy
]

# RegEx pro URL
URL_RE = re.compile(r'(https?://[^\s\)]+)', re.IGNORECASE)

def remove_technical_phrases(text):
    for phrase in TECHNICAL_PHRASES:
        text = re.sub(phrase, '', text, flags=re.IGNORECASE)
    return text

def extract_useful_sentences(text):
    # jednoduchá heuristika: rozděl na věty a vyber ty, které obsahují klíčová slova
    # nebo mají informativní význam (date, price, new, update, zmínky o událostech atd.)
    # uprav dle domény; tady použijeme jednoduché filtrování stop‑phrases a délky
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    useful = []
    for s in sentences:
        s_stripped = s.strip()
        if not s_stripped:
            continue
        # odfiltrovat příliš krátké/neinformatívní věty a technické fráze
        if len(s_stripped) < 30:
            continue
        if re.search(r'\b(unsubscribe|odhlásit|preferences|nastavení)\b', s_stripped, re.IGNORECASE):
            continue
        useful.append(s_stripped)
    return useful

def replace_links_with_anchor(text):
    # nahradí URL vložením "(<a ...>odkaz zde</a>)" právě za textový úsek, kde byl odkaz
    # pokud jde o HTML input, nejprve z něj vyndáme čistý text; tady pracujeme s plain text
    def repl(m):
        url = m.group(1)
        # vrací token, který frontend zobrazí jako (odkaz zde) s target=_blank
        # použijeme malé značení, aby frontend mohl bezpečně vrátit HTML anchor
        return f' (odkaz zde: {url})'  # do backendu vracíme i URL v závorce; frontend nahradí za anchor
    return URL_RE.sub(repl, text)

def to_safe_html_paragraphs(sentences):
    # každou větu do samostatného <p>; escape pro bezpečnost
    paragraphs = []
    for s in sentences:
        # nahradit raw links (http...) za "(odkaz zde: URL)" pokud někde zůstanou
        s2 = replace_links_with_anchor(s)
        # případně odstraň HTML tagy nebo je ošetři
        s2 = BeautifulSoup(s2, "html.parser").get_text(separator=" ")
        s2 = escape(s2)
        # nahrazení výskytu "(odkaz zde: URL)" za skutečný anchor -> uděláme to jako placeholder
        s2 = re.sub(r'\(odkaz zde:\s*(https?://[^\s\)]+)\)', r'(<a href="\1" target="_blank" rel="noopener noreferrer">odkaz zde</a>)', s2)
        paragraphs.append(f'<p>{s2}</p>')
    return '\n'.join(paragraphs)

def build_clean_summary(raw_text):
    # 1) strip HTML pokud je
    soup = BeautifulSoup(raw_text, "html.parser")
    text = soup.get_text(separator="\n")
    # 2) odstran technické věci
    text = remove_technical_phrases(text)
    # 3) reduce whitespace
    text = re.sub(r'\n{2,}', '\n\n', text).strip()
    # 4) vyber užitečné věty
    useful = extract_useful_sentences(text)
    # 5) vytvoř bezpečné HTML s anchors (otevřít v novém okně)
    html = to_safe_html_paragraphs(useful)
    return html

# Příklad použití:
if __name__ == "__main__":
    sample = """
    Nezobrazuje se vám newsletter správně? Klikněte sem: https://example.com/view
    Dne 20. 1. máme novou funkci, která zlepší doručování emailů.
    Cena za službu byla snížena na 5 EUR.
    Odhlásit se zde: https://example.com/unsub
    """
    print(build_clean_summary(sample))
