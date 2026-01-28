#!/usr/bin/env python3
"""
Process an email file (.eml or plain text) and produce a cleaned extractive summary.
Usage:
  python scripts/process_email.py path/to/email.eml --sentences 4 --language czech
"""
import argparse
import re
from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup

# extractive summarizer (sumy)
try:
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.lex_rank import LexRankSummarizer
except Exception:
    PlaintextParser = Tokenizer = LexRankSummarizer = None

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

def clean_email_text(text):
    t = remove_quoted_text(text)
    t = remove_signature(t)
    t = normalize_whitespace(t)
    return t

def extractive_summary(text, sentences_count=3, language="czech"):
    if PlaintextParser is None:
        raise RuntimeError("sumy library not available. Install requirements.txt")
    parser = PlaintextParser.from_string(text, Tokenizer(language))
    summarizer = LexRankSummarizer()
    sents = summarizer(parser.document, sentences_count)
    return " ".join(str(s) for s in sents)

def first_n_sentences(text, n=3):
    s = re.split(r'(?<=[.!?])\s+', text.strip())
    return " ".join(s[:n])

def main():
    parser = argparse.ArgumentParser(description="Process and summarize an email (no OpenAI).")
    parser.add_argument("input", help="Path to .eml file or plain text file")
    parser.add_argument("--sentences", "-n", type=int, default=4, help="Number of sentences in summary (extractive)")
    parser.add_argument("--method", choices=["extractive", "firstn"], default="extractive", help="Summarization method")
    parser.add_argument("--language", default="czech", help="Language for tokenizer (sumy), e.g. 'czech' or 'english'")
    parser.add_argument("--output", "-o", help="Optional output file (if omitted, prints to stdout)")
    args = parser.parse_args()

    # read input
    content = ""
    try:
        if args.input.lower().endswith(".eml"):
            with open(args.input, "rb") as f:
                content = extract_text_from_raw_email_bytes(f.read())
        else:
            with open(args.input, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
    except FileNotFoundError:
        print(f"File not found: {args.input}")
        return

    cleaned = clean_email_text(content)
    if not cleaned:
        result = "No text content found after extraction/cleaning."
    else:
        if args.method == "firstn":
            result = first_n_sentences(cleaned, args.sentences)
        else:
            try:
                result = extractive_summary(cleaned, sentences_count=args.sentences, language=args.language)
            except Exception as e:
                # fallback
                result = first_n_sentences(cleaned, args.sentences)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Summary written to {args.output}")
    else:
        print("\n--- SUMMARY ---\n")
        print(result)

if __name__ == "__main__":
    main()
