# Minimal newsletter-aggregator (tadeasraha/newsletter)

Co tento skeleton dělá:
- jednou týdně (GitHub Actions) stáhne nové maily z inboxu (IMAP),
- vybere maily podle `config/sources.yaml` (pole `from_pattern`),
- extrahuje krátké shrnutí a první odkaz z mailu,
- fetchne odkaz (pokud existuje) a vezme krátké resumé stránky,
- provede (volitelně) AI reprioritizaci položek, pokud je nastaven `OPENAI_API_KEY`,
- vygeneruje jednoduchý HTML digest a pošle ho přes SMTP na adresu `IMAP_USER`,
- označí zpracované zprávy jako přečtené a přesune je do mailboxu "Newsletter 2",
- uloží processed message IDs do `data/state.json` (workflow commitne state.json zpět do repa).

Požadované GitHub Secrets:
- IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASSWORD
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
- COMMIT_USER_NAME, COMMIT_USER_EMAIL
- (volitelně) OPENAI_API_KEY

Jak přidat / upravit zdroje:
- Edituj `config/sources.yaml` a přidej položky:
  - id: jedinečný slug (bez mezer)
  - name: čitelný název
  - from_pattern: přesná adresa nebo wildcard: *@domain.com
  - priority: 1 (nejvyšší) .. 3 (nejnižší)
  - enabled: true/false
  - folder: "Newslettery"

Jak otestovat lokálně:
1. Vytvoř virtuální prostředí a nainstaluj dependencies:
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
2. Nastav env proměnné (neukládej hesla do repa).
3. Spusť:
   python -m src.main

Jak vytvořit PR (lokálně pomocí git + gh):
- git checkout -b feature/minimal-skeleton
- přidej soubory (nebo je vlož přes web)
- git add .
- git commit -m "Add minimal newsletter aggregator skeleton"
- git push -u origin feature/minimal-skeleton
- gh pr create --title "Add minimal newsletter aggregator skeleton" --body "Minimal skeleton + config prepopulated." --base main

Poznámky:
- AI reprioritizace se spustí pouze pokud je nastaven `OPENAI_API_KEY`. Model a prompt jsou jednoduché — slouží jako pomocné skóre.
- Pokud server IMAP nepodporuje MOVE, použije se fallback copy+mark+delete+expunge.
- Archivní mailbox je nyní nastaven na "Newsletter 2" (pokud budeš chtít jiný název, uprav `src/config.py`).
