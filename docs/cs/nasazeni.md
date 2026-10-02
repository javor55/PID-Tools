# Nasazení a provoz

PID Tools běží jako webová aplikace ([Streamlit](https://streamlit.io/): server v Pythonu, uživatelé pracují
v prohlížeči) nebo jako desktopová aplikace (okno bez prohlížeče a bez síťového portu – vhodné pro inženýrské
stanice). Obě používají stejné výpočty a stejné projektové soubory.

| Způsob | Pro koho | Data |
|---|---|---|
| **Veřejná instance** (Streamlit Community Cloud) | rychlé vyzkoušení, ukázková a necitlivá data | odcházejí na cizí server |
| **Lokálně na PC** | jednotlivý inženýr | zůstávají na vlastním PC |
| **Offline PC / inženýrská stanice** (přenosný balíček přes USB, desktop nebo web) | PC bez internetu, inženýrské stanice PCS 7 | zůstávají na PC |
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

## Offline PC a inženýrská stanice (USB)

Pro PC bez internetu je **přenosný balíček pro Windows (x64)**: složka s vlastním Pythonem, všemi knihovnami
a aplikací. Nic se neinstaluje, nejsou potřeba práva správce.

1. Na PC s internetem stáhněte `PID-Tools-<verze>-win64-offline.zip` (asi 300 MB) z **Releases** repozitáře na
   GitHubu nebo z posledního běhu workflow *Offline package (Windows)* (záložka *Actions* › běh › *Artifacts*;
   artefakt je ZIP, ve kterém je ZIP balíčku).
2. Přeneste ho na offline PC (USB) a rozbalte, např. do `C:\Tools\PID-Tools` (ne do příliš dlouhé cesty).
3. **Desktopová aplikace:** dvojklik na **`PID-Tools-desktop.bat`** – otevře se okno (bez prohlížeče, bez síťového
   portu, nic neběží na pozadí). Datový soubor nebo projekt lze na `.bat` přetáhnout a rovnou otevřít.
4. **Webová aplikace** (stejné funkce v prohlížeči): dvojklik na **`PID-Tools.bat`**. Konzolové okno spustí aplikaci
   a prohlížeč otevře <http://localhost:8501>. Zavřením konzole se aplikace ukončí.

Balíček vyžaduje Windows 10 nebo 11 (x64). Odinstalace = smazání složky, aktualizace = nahrazení složky novějším
balíčkem (projekty v JSON zůstávají kompatibilní).

**Sestavení balíčku** (PC s Windows, internetem a Pythonem 3.11):
```bash
python tools/build_offline.py               # -> dist/PID-Tools-<verze>-win64-offline.zip
python tools/build_offline.py --no-desktop  # jen webová aplikace, bez Qt (menší)
```
Totéž dělá na GitHubu workflow `.github/workflows/offline-package.yml`: sestaví balíček na Windows, otestuje ho jeho
vlastním Pythonem (jádro, celá webová aplikace i okna desktopu na ukázkových datech, start serveru) a zveřejní ho
jako artefakt; u tagu verze (`v*`) ho přiloží k release.

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
