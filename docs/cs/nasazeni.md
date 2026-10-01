# Nasazení a provoz

PID Tools je aplikace ve [Streamlitu](https://streamlit.io/): server v Pythonu, uživatelé pracují v prohlížeči.
Lze ji provozovat třemi způsoby.

| Způsob | Pro koho | Data |
|---|---|---|
| **Veřejná instance** (Streamlit Community Cloud) | rychlé vyzkoušení, ukázková a necitlivá data | odcházejí na cizí server |
| **Lokálně na PC** | jednotlivý inženýr | zůstávají na vlastním PC |
| **Interní server** | tým / firma | zůstávají ve firemní síti |

---

## Veřejná instance

<https://pidtools.streamlit.app/> – aktualizuje se automaticky z větve repozitáře, ze které je nasazená
(obvykle `main`). Nic se neinstaluje.
Přístup lze v nastavení aplikace na Streamlit Community Cloud omezit na pozvané uživatele (podle podmínek služby).
Než tam nahrajete provozní data, ověřte, že to pravidla vaší firmy dovolují.

## Lokálně na PC

**Windows**
1. Nainstalujte [Python 3.11](https://www.python.org/downloads/) (zaškrtněte *Add Python to PATH*).
2. Stáhněte repozitář (*Code › Download ZIP*) a rozbalte.
3. Spusťte `start.bat` – při prvním spuštění nainstaluje knihovny (vyžaduje přístup na PyPI), pak otevře
   aplikaci na <http://localhost:8501>.

Ve firemní síti s proxy nastavte pro pip proxy (`pip config set global.proxy http://proxy:port`) nebo si
nechte knihovny nainstalovat správcem.

**Linux / macOS**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Interní server

Aplikace **nemá vlastní přihlašování** – pro sdílení v týmu ji provozujte ve firemní síti, případně za reverzní
proxy s přihlášením (např. přes firemní SSO) a HTTPS.

**Přímo v Pythonu** (např. jako služba systemd):
```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

**Docker** (soubor `Dockerfile` je v repozitáři):
```bash
docker build -t pid-tools .
docker run -d --name pid-tools -p 8501:8501 --restart unless-stopped pid-tools
```
Kontrola stavu: `http://server:8501/_stcore/health` vrací `ok`.

**Nároky (orientačně):** jedna relace zabere řádově stovky MB paměti (velké exporty víc); optimalizace
a gain scheduling krátce vytíží jedno jádro CPU. Pro malý tým by měla stačit 2 jádra a 2–4 GB RAM.

## Konfigurace

`.streamlit/config.toml`:

| Volba | Nastavení | Proč |
|---|---|---|
| `browser.gatherUsageStats` | `false` | žádná telemetrie Streamlitu |
| `client.toolbarMode` | `viewer` | uživatelé nevidí vývojářské volby |
| `server.maxUploadSize` | `200` (MB) | velikost nahrávaného exportu |
| `[theme.light]`, `[theme.dark]` | barvy | světlý a tmavý vzhled (přepíná uživatel v menu ⋮) |

## Data a soukromí

- Nahraná data se zpracovávají jen v paměti serveru po dobu relace (a v mezipaměti výpočtů); aplikace nic
  nezapisuje na disk a nevolá žádné externí služby.
- Rozpracovaná práce se automaticky ukládá **v prohlížeči uživatele** (IndexedDB) – ne na serveru. Uživatel ji
  může vypnout nebo smazat v záložce Projekt a report.
- Projekt (JSON) a protokol (HTML) se stahují do počítače uživatele. Protokol s volbou „grafy z internetu“ načítá
  knihovnu grafů z CDN při otevření; výchozí volba („vložené“) funguje offline.

## Aktualizace

- **Veřejná instance** se aktualizuje sama.
- **Lokálně:** stáhněte novou verzi (nebo `git pull`) a spusťte znovu; `start.bat` doinstaluje knihovny.
- **Docker:** znovu sestavte obraz a spusťte kontejner.

Projekty uložené starší verzí aplikace jdou načíst i v nové verzi. Verze aplikace je v *Nápověda › O aplikaci*
a v patičce protokolu; změny popisuje [CHANGELOG](CHANGELOG.md).

## Vývoj a testy

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```
Testy pokrývají výpočetní jádro, načítání dat, celou aplikaci (Streamlit AppTest) a shodu živé simulace
v prohlížeči s výpočtem v Pythonu (vyžaduje Node.js; bez něj se test přeskočí).
