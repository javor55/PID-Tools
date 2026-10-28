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

Pro PC bez internetu jsou dva soubory ke stažení pro **Windows (x64)**. Oba obsahují vše potřebné (Python, knihovny,
aplikaci); není potřeba internet ani práva správce. Stáhněte je na PC s internetem z **Releases** repozitáře na
GitHubu nebo z posledního běhu workflow *Offline package (Windows)* (záložka *Actions* › běh › *Artifacts*;
artefakt je ZIP, ve kterém jsou soubory balíčku).

**Desktopová aplikace** (okno, bez prohlížeče, bez síťového portu) – klasická aplikace pro Windows s vlastní ikonou:

- `PID-Tools-<verze>-setup.exe` – instalátor pro přihlášeného uživatele (bez práv správce): nainstaluje do
  `%LOCALAPPDATA%\Programs\PID Tools`, přidá PID Tools do nabídky Start (volitelně na plochu) a do *Nastavení ›
  Aplikace* pro odinstalaci. Spuštění: **PID Tools** v nabídce Start.
- `PID-Tools-<verze>-desktop-win64-portable.zip` – totéž bez instalace: rozbalte (např. na USB nebo do `C:\Tools`)
  a spusťte **`PID Tools.exe`**. Datový soubor nebo projekt lze na exe přetáhnout a rovnou otevřít.

**Webová aplikace offline** (stejné funkce v prohlížeči na tomto PC):

- `PID-Tools-<verze>-web-win64-offline.zip` – rozbalte, např. do `C:\Tools\PID-Tools-web` (ne do příliš dlouhé
  cesty), a dvakrát klikněte na **`PID-Tools.bat`**. Konzolové okno spustí aplikaci a prohlížeč otevře
  <http://localhost:8501>. Zavřením konzole se aplikace ukončí. Obsahuje i zdroj dat OPC UA.

Windows 10 nebo 11 (x64). Přenosné verze odstraníte smazáním složky, aktualizujete nahrazením složky (nebo novějším
instalátorem). Projekty v JSON zůstávají kompatibilní a jsou zaměnitelné mezi desktopem a webem.

**Sestavení balíčků** (PC s Windows, internetem a Pythonem 3.11):
```bash
pip install -r requirements.txt -r requirements-desktop.txt pyinstaller
python tools/build_desktop.py   # -> dist/PID Tools/PID Tools.exe, přenosný ZIP, instalátor (potřebuje Inno Setup 6)
python tools/build_offline.py   # -> dist/PID-Tools-<verze>-web-win64-offline.zip
```
Totéž dělá na GitHubu workflow `.github/workflows/offline-package.yml`: obojí sestaví na Windows, otestuje (exe
desktopu spustí vlastní kontrolu `--smoke`, webový balíček projde jádro i celou aplikaci vlastním Pythonem a spustí
server) a zveřejní jako artefakty; u tagu verze (`v*`) je přiloží k release.

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

## Web pro tým (nové rozhraní, kontejner)

Nové rozhraní (API FastAPI + sestavené UI v Reactu) běží jako **jeden kontejner** s přihlášením: každý pracovní
prostor a úloha patří uživateli, který je vytvořil (cizí ID dává 404). Podrobný návod je anglicky v
[deployment.md](../deployment.md#team-web-new-ui-container); stručně:

```bash
docker build -f Dockerfile.web -t pid-tools-web .
docker run -d --name pid-tools-web --restart unless-stopped -p 127.0.0.1:8080:8080 \
  -e PIDTOOLS_AUTH=cloudflare -e PIDTOOLS_CF_TEAM=vasetym -e PIDTOOLS_CF_AUD=<audience tag> pid-tools-web
```

- **Cloudflare Access** (výchozí volba R3): aplikaci (Self-hosted, hostname za tunelem `cloudflared`) a pravidlo
  *Allow* nastavíte v Zero Trust; **team domain** (`vasetym.cloudflareaccess.com`) je v *Settings*, **AUD tag**
  v nastavení aplikace. Aplikace sama ověří podpis JWT v hlavičce `Cf-Access-Jwt-Assertion` (klíče z JWKS týmu);
  bez platného tokenu odpoví 401.
- Jiné proxy s přihlášením (OIDC): `PIDTOOLS_AUTH=header` důvěřuje hlavičce s uživatelem (`PIDTOOLS_USER_HEADER`) jen po
  výslovném `PIDTOOLS_TRUST_USER_HEADER=1`; hlavička není podepsaná, kontejner proto musí být dostupný jen z proxy.
- Limity: `PIDTOOLS_MAX_WORKSPACES_USER` (5), `PIDTOOLS_MAX_JOBS_USER` (2), `PIDTOOLS_MAX_JOBS` (2),
  `PIDTOOLS_MAX_UPLOAD_MB` (100), `PIDTOOLS_WORKSPACE_TTL` (3600 s nečinnosti), `PIDTOOLS_LOG_LEVEL` (INFO).
- Logy (`docker logs`): řádek na požadavek s uživatelem, metodou, cestou, stavem a trváním, a začátek a konec úloh.
- Běží jeden proces (prostory a úlohy jsou v paměti): po restartu je nutné projekt znovu otevřít, proto uživatelé
  průběžně ukládají projekt.

## Konfigurace (Streamlit)

`.streamlit/config.toml`:

| Volba | Nastavení | Proč |
|---|---|---|
| `browser.gatherUsageStats` | `false` | žádná telemetrie Streamlitu |
| `client.toolbarMode` | `viewer` | uživatelé nevidí vývojářské volby |
| `server.maxUploadSize` | `100` (MB) | velikost nahrávaného exportu |
| `[theme.light]`, `[theme.dark]` | barvy | světlý a tmavý vzhled (přepíná uživatel v menu ⋮) |

## Data a soukromí

- Nahraná data se zpracovávají jen v paměti serveru po dobu relace (a v mezipaměti výpočtů); aplikace nic
  nezapisuje na disk a nevolá žádné externí služby.
- Webová aplikace rozpracovanou práci neukládá – uživatel si ji uloží jako projekt (soubor JSON).
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
