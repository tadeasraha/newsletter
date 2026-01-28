# Newsletter Agregátor

Automatický systém pro sběr, zpracování a agregaci newsletterů do týdenního HTML digestu.

## 📋 Funkce

- **Automatické stahování**: Každý pátek v 7:00 UTC stáhne nové newslettery z IMAP serveru
- **Chytré zpracování**: Extrahuje odkazy, načítá články a vytváří jejich souhrny
- **AI prioritizace**: Volitelně používá OpenAI API pro inteligentní řazení podle důležitosti
- **Archivace**: Zpracované zprávy označí jako přečtené a přesune do archivní složky
- **HTML digest**: Vygeneruje pěkně formátovaný HTML e-mail s přehledem
- **Automatické odesílání**: Odešle digest přes SMTP

## 🚀 Nastavení

### 1. Secrets v GitHub

V nastavení repozitáře (Settings → Secrets and variables → Actions) přidejte následující secrets:

#### Povinné secrets:

- `IMAP_SERVER` - IMAP server (např. `imap.gmail.com`)
- `IMAP_PORT` - IMAP port (obvykle `993`)
- `IMAP_USER` - E-mailová adresa pro IMAP
- `IMAP_PASSWORD` - Heslo pro IMAP
- `SMTP_SERVER` - SMTP server (např. `smtp.gmail.com`)
- `SMTP_PORT` - SMTP port (obvykle `587`)
- `SMTP_USER` - E-mailová adresa pro SMTP
- `SMTP_PASSWORD` - Heslo pro SMTP
- `COMMIT_USER_NAME` - Jméno pro Git commity (např. `Newsletter Bot`)
- `COMMIT_USER_EMAIL` - E-mail pro Git commity (např. `bot@newsletter.local`)

#### Volitelné secrets:

- `OPENAI_API_KEY` - OpenAI API klíč pro AI prioritizaci (pokud není nastaven, použije se pouze ruční priorita)

### 2. Konfigurace zdrojů

Upravte soubor `config/sources.yaml` podle svých potřeb:

```yaml
sources:
  - id: "example"
    name: "Example Newsletter"
    from_pattern: "example"  # Hledá tento text v e-mailové adrese odesílatele (case-insensitive)
    priority: 1  # 1 = nejvyšší, 3 = nejnižší
    enabled: true
    folder: "Newslettery"  # Složka v IMAP, kde hledat zprávy
```

**Parametry zdroje:**
- `id` - Unikátní identifikátor (slug)
- `name` - Zobrazované jméno
- `from_pattern` - Text pro hledání v adrese odesílatele
- `priority` - Priorita 1-3 (1 = nejvyšší)
- `enabled` - `true` pro aktivní, `false` pro deaktivovaný zdroj
- `folder` - Složka v IMAP serveru

### 3. Lokální testování

Pro lokální testování vytvořte soubor `.env` s secrets:

```env
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your-email@gmail.com
IMAP_PASSWORD=your-password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-password
OPENAI_API_KEY=sk-...
COMMIT_USER_NAME=Newsletter Bot
COMMIT_USER_EMAIL=bot@newsletter.local
```

Pak nainstalujte závislosti a spusťte:

```bash
pip install -r requirements.txt
python -m src.main
```

## 🤖 GitHub Actions

Workflow běží automaticky každý pátek v 7:00 UTC. Můžete ho také spustit manuálně:

1. Jděte na záložku **Actions** v repozitáři
2. Vyberte workflow **Weekly Newsletter Digest**
3. Klikněte na **Run workflow**

## 📁 Struktura projektu

```
.
├── .github/
│   └── workflows/
│       └── weekly_digest.yml    # GitHub Actions workflow
├── config/
│   └── sources.yaml             # Konfigurace zdrojů
├── src/
│   ├── __init__.py
│   ├── config.py                # Načítání konfigurace
│   ├── state.py                 # Správa stavu (state.json)
│   ├── imap_ingest.py           # Načítání z IMAP
│   ├── fetcher.py               # Načítání článků z webu
│   ├── generator.py             # Generování HTML
│   ├── send.py                  # Odesílání e-mailů
│   ├── ai_reprio.py             # AI re-prioritizace
│   └── main.py                  # Hlavní orchestrace
├── requirements.txt             # Python závislosti
├── state.json                   # Stav zpracovaných zpráv (generuje se automaticky)
└── README.md                    # Tento soubor
```

## 🔄 Jak to funguje

1. **Stahování**: Systém se připojí k IMAP serveru a načte nepřečtené zprávy ze složky definované v konfiguraci
2. **Filtrování**: Zprávy se filtrují podle `from_pattern` z konfigurace
3. **Extrakce**: Z každé zprávy se extrahuje první odkaz a načte se obsah článku
4. **AI analýza** (volitelně): Pokud je nastaven `OPENAI_API_KEY`, použije se AI pro hodnocení důležitosti podle kritérií:
   - Akčnost (actionability)
   - Blížící se uzávěrka (deadline)
   - Důležitost pro učení (learning value)
   - Potřebnost (need)
5. **Řazení**: Položky se seřadí podle priority a AI skóre
6. **Generování**: Vytvoří se HTML digest s pěkným formátováním
7. **Odesílání**: Digest se odešle na e-mail (výchozí je `IMAP_USER`)
8. **Archivace**: Zpracované zprávy se označí jako přečtené a přesunou do složky "Newsletter 2"
9. **Uložení stavu**: Stav se uloží do `state.json` a commitne do repozitáře

## 📝 Poznámky

- Zprávy jsou po zpracování přesunuty do archivní složky "Newsletter 2"
- Pokud server nepodporuje MOVE operaci, použije se fallback: COPY + DELETE + EXPUNGE
- Stav zpracovaných zpráv se ukládá do `state.json` pro prevenci duplicit
- AI prioritizace je volitelná - bez API klíče se použije pouze ruční priorita ze `sources.yaml`

## 📄 Licence

MIT
