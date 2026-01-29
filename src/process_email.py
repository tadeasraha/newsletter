#!/usr/bin/env python3
"""
Local email extractor + extractive summarizer (no OpenAI).
Usage: python src/process_email.py path/to/email.eml --sentences 4
Requires: beautifulsoup4, sumy, nltk
"""
import argparse
import re
from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup

try:
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.lex_rank import LexRankSummarizer
except Exception:
    PlaintextParser = Tokenizer = LexRankSummarizer = None

URL_RE = re.compile(r'(https?://[^\s\)]+)', re.IGNORECASE)

def extract_text_from_raw_email_bytes(raw_bytes):
    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                parts.append(payload.decode(charset, errors="replace"))
            elif ctype == "text/html" and "attachment" not in disp:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace")
                text = BeautifulSoup(html, "html.parser").get_text(separator="\n")
                parts.append(text)
    else:
        ctype = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if ctype == "text/html":
                text = BeautifulSoup(text, "html.parser").get_text(separator="\n")
            parts.append(text)
    return "\n\n".join(parts).strip()

def remove_quoted_text(text):
    lines = []
    for line in text.splitlines():
        if line.strip().startswith(">"):
            continue
        if re.match(r'On .* wrote:', line):
            break
        lines.append(line)
    return "\n".join(lines)

def remove_signature(text):
    markers = [r'\n--\s*\n', r'\nS pozdravem', r'\nDěkuji,', r'\nRegards,', r'\nBest,']
    for m in markers:
        match = re.search(m, text, flags=re.IGNORECASE)
        if match:
            return text[:match.start()].strip()
    return text

def normalize_whitespace(text):
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()

def replace_links_with_placeholder(text):
    def repl(m):
        url = m.group(1)
        return f' (odkaz zde: {url})'
    return URL_RE.sub(repl, text)

def clean_email_text(text):
    t = remove_quoted_text(text)
    t = remove_signature(t)
    t = normalize_whitespace(t)
    t = replace_links_with_placeholder(t)
    return t

def extractive_summary(text, sentences_count=3, language="czech"):
    if PlaintextParser is None:
        raise RuntimeError("sumy library not available. Install dependencies (beautifulsoup4, sumy, nltk).")
    parser = PlaintextParser.from_string(text, Tokenizer(language))
    summarizer = LexRankSummarizer()
    sents = summarizer(parser.document, sentences_count)
    useful = []
    for s in sents:
        s_str = str(s).strip()
        if len(s_str) < 40:
            continue
        if re.search(r'\b(unsubscribe|odhlásit|preferences|nastavení|newsletter)\b', s_str, re.IGNORECASE):
            continue
        useful.append(s_str)
    return useful

def to_safe_paragraphs(sentences):
    paragraphs = []
    for s in sentences:
        s = re.sub(r'\(odkaz zde:\s*(https?://[^\s\)]+)\)', r'(<a href="\1" target="_blank" rel="noopener noreferrer">odkaz zde</a>)', s)
        s = s.replace("\r", "").strip()
        paragraphs.append(f'<p>{s}</p>')
    return "\n".join(paragraphs)

def process_file(path, sentences=4, language="czech"):
    if path.lower().endswith(".eml"):
        with open(path, "rb") as f:
            raw = f.read()
        raw_text = extract_text_from_raw_email_bytes(raw)
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()
    cleaned = clean_email_text(raw_text)
    if not cleaned.strip():
        return "No text content found after extraction/cleaning."
    try:
        useful = extractive_summary(cleaned, sentences_count=sentences, language=language)
    except Exception:
        sents = re.split(r'(?<=[.!?])\s+', cleaned.strip())
        useful = [x for x in sents if len(x.strip())>30][:sentences]
    if not useful:
        return "Žádné nové užitečné informace."
    html = to_safe_paragraphs(useful)
    return html

def main():
    parser = argparse.ArgumentParser(description="Process and summarize an email (no OpenAI).")
    parser.add_argument("input", help="Path to .eml file or plain text file")
    parser.add_argument("--sentences", "-n", type=int, default=4, help="Number of sentences in summary (extractive)")
    parser.add_argument("--language", default="czech", help="Language for tokenizer (sumy), e.g. 'czech' or 'english'")
    parser.add_argument("--output", "-o", help="Optional output file (if omitted, prints to stdout)")
    args = parser.parse_args()

    result = process_file(args.input, sentences=args.sentences, language=args.language)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Summary written to {args.output}")
    else:
        print("\n--- SUMMARY ---\n")
        print(result)

if __name__ == "__main__":
    main()
