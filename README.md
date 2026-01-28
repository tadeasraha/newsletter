# Minimal newsletter-aggregator (tadeasraha/newsletter)

Co tento skeleton dělá:
- jednou týdně (GitHub Actions) stáhne nové maily z inboxu (IMAP),
- vybere maily podle `config/sources.yaml` (pole `from_pattern`),
- extrahuje krátké shrnutí a první odkaz z mailu,
- fetchne odkaz (pokud existuje) a vezme krátké resumé stránky,
- vygeneruje jednoduchý HTML digest a pošle ho přes SMTP na tvůj email,
- uloží processed message IDs do `data/state.json` (commitnuto zpět do repa).

Jak spustit:
1. Přidej secrets do repo (už máš): IMAP_*, SMTP_*, COMMIT_*, (volitelně) OPENAI_API_KEY.
2. Přidej zdroje: uprav `config/sources.yaml` (přidej entries do pole `sources`).
3. Mergni PR s tímto skeletonem nebo nahraj soubory ručně.
4. V Actions spusť workflow manuálně pro test (Actions → Weekly digest → Run workflow).
5. Po úspěchu bude digest poslán na tvůj email.

Poznámky:
- Priorita: 1..5. Pokud v `config/sources.yaml` chybí, použije se default = 3.
- LLM shrnutí: pokud máš `OPENAI_API_KEY`, můžeme doplnit abstractive shrnutí pro top položky. Zatím používáme extractive fallback.
- Pokud chceš, abych to nahrál jako PR, napiš „Vytvoř PR".
