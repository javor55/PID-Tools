# Milníky přechodu na jedno rozhraní a profesionální nasazení

Prováděcí plán k [plan-jednotne-ui.md](plan-jednotne-ui.md). Práce je rozdělená na **malé milníky**. Každý má
být jeden PR, který se dá dokončit v jednom až třech pracovních sezeních.

**Pravidla:**
- Každý milník končí **zeleným CI a merge do `main`**.
- Stará aplikace (Streamlit web a PySide6 desktop) **běží celou dobu**, dokud ji M28 nevypne.
- Rozpracovaný milník se nenechává v `main` napůl: buď je hotový, nebo zůstane ve větvi.
- Výpočty v `pidtools/core` a `pidtools/app` se nepřepisují. Mění se jen jejich obal a místo, kde žije stav.
- Pořadí uvnitř fáze je doporučené. Milníky bez vzájemné závislosti lze přeskočit nebo prohodit.

**Velikost:**
- S ≈ 1 sezení;
- M ≈ 2 sezení;
- L ≈ 3 a více sezení. Milník velikosti L se při práci dělí na části (a, b, …), každá je samostatný PR.

**Stav:**
- ☐ čeká;
- ◐ rozpracováno (větev, PR);
- ☑ hotovo (zmergováno).

## Přehled

| # | Milník | Fáze | Velikost | Závisí na | Stav |
|---|---|---|---|---|---|
| M1 | Zlaté případy | A | M | – | ◐ |
| M2 | Přibalené fonty (offline) | A | S | – | ◐ |
| M3 | Texty CZ / EN do JSON | A | S | – | ☐ |
| M4 | Pracovní prostor v `app` (stav bez UI) | A | L | M1 | ☐ |
| M5 | Úlohy s průběhem a zrušením, cache | A | M | M4 | ☐ |
| M6 | Kostra API (FastAPI, token, OpenAPI) | B | M | M4 | ☐ |
| M7 | API: data a signály | B | M | M6 | ☐ |
| M8 | API: projekt | B | S | M6 | ☐ |
| M9 | API: model | B | L | M5, M7 | ☐ |
| M10 | API: ladění, scénář, robustnost, frekvence | B | L | M9 | ☐ |
| M11 | API: APC, diagnostika, přehled smyček, report, OPC UA | B | L | M10 | ☐ |
| M12 | Kostra frontendu (TS, design, téma, jazyk) | C | M | M3, M6, **R1** | ☐ |
| M13 | Záložka Data + prohlížeč záznamu | C | M | M7, M12 | ☐ |
| M14 | Model 1: úseky, identifikace, výsledky | C | L | M9, M13 | ☐ |
| M15 | Model 2: karty přenosů, úpravy, validace, nejistota | C | L | M14 | ☐ |
| M16 | Ladění 1: blok PIDConL, sady, návrh, kontroly | C | M | M10, M15 | ☐ |
| M17 | Ladění 2: porovnání, scénář, robustnost, frekvence | C | L | M16 | ☐ |
| M18 | Živá simulace | C | M | M16 | ☐ |
| M19 | APC | C | L | M11, M16 | ☐ |
| M20 | Diagnostika a Přehled smyček | C | M | M11, M13 | ☐ |
| M21 | Projekt, report, OPC UA | C | M | M8, M11 | ☐ |
| M22 | Backend jako samostatný program (sidecar) | D | M | M6 | ☐ |
| M23 | Okno desktopu (Tauri) | D | M | M12, M22, **R2** | ☐ |
| M24 | Instalátor, WebView2, podpis, release | D | M | M23, **R4**, **R6** | ☐ |
| M25 | Offline ověření na čistém Windows | D | S | M24 | ☐ |
| M26 | Webové nasazení pro tým (kontejner, přihlášení, limity) | D | M | M12, **R3** | ☐ |
| M27 | Parita a pilot | E | M | M13–M21, M25 | ☐ |
| M28 | Vypnutí staré aplikace, verze 4.0 | E | M | M27 | ☐ |

**R1–R6** jsou rozhodnutí z kap. 8 plánu (viz [Rozhodnutí](#rozhodnutí)). Fáze A se dá dělat hned, bez ohledu
na ně, a prospěje i dnešní aplikaci.

## Zjištění během práce

Chyby a omezení výpočtů nalezené při přípravě. Opravené se uvádí u milníku, ostatní čekají na samostatný PR.

| Kde | Zjištění | Stav |
|---|---|---|
| M1 | Režim dat *Automaticky* volil uzavřenou smyčku i se Set 1 na výchozích hodnotách (Gain 1, TI 100) – simulace smyčky s nesprávným regulátorem dala nesmyslný model (FIT −27 %, otevřená smyčka 87 %). | opraveno v M1: AUTO jen se skutečným Set 1, jinak upozornění |
| M1 | Uložení projektu s daty a jeho opětovné načtení ubralo jeden vzorek (zaokrouhlení počtu vzorků při převzorkování). | opraveno v M1 |
| M1 | Identifikace v uzavřené smyčce (nepřímá i kombinovaná) občas uvízne v lokálním minimu dopravního zpoždění (θ → 0) podle toho, kde úsek začíná. | čeká – robustnější hledání θ (víc startů, kontrola přes ruční úseky) |
| M1 | Kombinovaná identifikace s nesprávně škálovaným Set 1 (rozsahy NormPV / NormMV) zhorší i dobrý model z ručních úseků (TIC001: θ 364 s → 0). Upozorní jen kontrola „zpoždění ≈ 0“. | čeká – varování / vyšší váha ručních úseků, když AUTO úseky shodu zhoršují |
| M1 | Vyřazení dat podle mezí PV při rozsahu, který data nepokrývá (TIC001: rozsah 0–100, teplota 98–101 °C), tiše vyřadí většinu vzorků úseku. | čeká – upozornění na nízký podíl platných vzorků v úseku |

---

## Fáze A – příprava v dnešním kódu

### M1 · Zlaté případy
Uložené výsledky dnešní verze, se kterými se porovná API i nové UI. Dokud je dnešní aplikace jediným zdrojem
pravdy, je potřeba je zachytit hned.
- `tools/golden.py` projde sadu projektů a uloží výsledky do `tests/golden/*.json`:
  - kvalita dat;
  - modely všech struktur (parametry, FIT): společný úsek, úseky podle vstupů, uzavřená smyčka, kombinovaná identifikace;
  - návrhy ladění (metody, KPI);
  - simulace scénáře;
  - robustnost a frekvenční charakteristiky;
  - APC návrhy;
  - diagnostika.
- Sada projektů: demo, `suseni.csv`, APC příklady, syntetické případy (otevřená, uzavřená a kombinovaná smyčka,
  integrační proces, porucha).
- Uživatelská data bez souhlasu nepřidávat. TT363 jen se souhlasem, případně anonymizované.
- `tests/test_golden.py` přepočítá výsledky a porovná je s tolerancí. Regenerace je záměrná:
  `python tools/golden.py --update`.

**Hotovo když:** test běží v CI do 2 min a pokrývá každou záložku aspoň jedním případem.

**Skutečnost:** 8 případů:
- demo (společný úsek a úseky podle vstupů);
- `ff_example` (data jsou v AUTO, ale Set 1 není vyplněn);
- TIC001 / TIC002 (anonymizovaný reálný projekt): uložený úsek, ruční úsek a kombinovaná identifikace;
- syntetická uzavřená a kombinovaná smyčka.

Výsledky každého případu: data, kvalita, MAN / AUTO, modely, návrhy ladění s kontrolami, robustnost Set 1, scénář,
frekvence, u části i diagnostika a APC (doporučení, Smith). Navíc test uložení a načtení projektu (i formát v1).
Výpočet trvá ≈ 90 s. Přehled smyček a report nemají vlastní výpočet, ověří je M4d / M11.

### M2 · Přibalené fonty
- IBM Plex Sans a Mono (woff2, licence OFL) do `pidtools/ui/static/fonts`; `@font-face` v `theme.py`.
- Odstranit stahování z Google Fonts (`.streamlit/config.toml`). Ověřit offline balíček bez sítě.

**Hotovo když:** web i offline balíček nemají žádný požadavek mimo vlastní server (kontrola v Playwright testu).

**Skutečnost:**
- `static/fonts`: IBM Plex Sans (400, 400 kurzíva, 500, 600) a Mono (400, 500, 600), podmnožiny latin a latin-ext
  (čeština), ≈ 280 kB, licence OFL u souborů.
- Fonty se servírují přes `theme.fontFaces` a `server.enableStaticServing`; jsou v Dockerfile i v offline balíčku.
- `test_offline_no_external_requests` zaznamená všechny požadavky stránky a ověří načtení fontu.

### M3 · Texty do JSON
- `pidtools/i18n/cs.json` a `en.json` jako jediný zdroj. Rozhraní `T()` se nemění, `cs.py` a `en.py` se odstraní.
- Test shody klíčů a placeholderů `{x}` mezi jazyky.

**Hotovo když:** obě dnešní UI a report fungují beze změny a nový frontend může JSON načíst přímo.

### M4 · Pracovní prostor v `app` (L, dělí se na a–d)
Dnes je stav a workflow zdvojený:
- desktop: `desktop/state.py`, ≈ 900 řádků;
- web: `ui/pages/*.py` a `ui/context.py`.

Cílem je jedna třída **`pidtools/app/workspace.py`**: data, sloupce, úseky, nastavení, fit, ladění. Je bez
Qt i Streamlitu a serializuje se do formátu projektu. API ji pak jen obalí. Desktop `state.py` se zúží na tenký
obal nad ní; web ji začne používat tam, kde to nevyžaduje přestavbu stránek.
- **M4a** – data, sloupce, převzorkování, úsek (společný i podle vstupů), vyřazení dat, kvalita dat.
- **M4b** – identifikace: otevřená, uzavřená a kombinovaná smyčka, režim MAN / AUTO, dofitování, porovnání
  struktur, křížové ověření, nejistota, klíč aktuálnosti modelu.
- **M4c** – ladění: blok PIDConL, sady, metody, kontroly; dále scénář, dopředná vazba, robustnost a frekvence.
- **M4d** – APC, diagnostika, přehled smyček; uložení a načtení projektu přes workspace.

**Hotovo když:** desktop běží nad workspace, zlaté případy (M1) projdou přes workspace a stávající testy jsou zelené.

### M5 · Úlohy a cache
- `pidtools/app/jobs.py`: dlouhé výpočty (identifikace, optimalizace ladění, nejistota, APC) v procesech, s průběhem
  (0–100 % a text), zrušením a časovým limitem.
- Cache výsledků podle klíče vstupů (logika z `ui/cache.py`) s limitem paměti.

**Hotovo když:** úlohu jde zrušit do 1 s a výsledek z cache se vrátí bez přepočtu (test).

---

## Fáze B – API (`pidtools/api`, FastAPI)

### M6 · Kostra API
- Aplikace FastAPI:
  - `/health`;
  - pracovní prostor: vytvořit, smazat, vypršení po nečinnosti;
  - texty (`/i18n/{lang}`);
  - úlohy (`/jobs/{id}`: stav, průběh přes SSE, zrušení).
- Bezpečnost pro desktop:
  - poslouchá jen na `127.0.0.1`;
  - port zadaný při spuštění;
  - token v hlavičce;
  - CORS jen pro okno aplikace.
- Generovaný `openapi.json` je v repozitáři a CI selže, když se API změní bez jeho přegenerování.
- Testy pytest a httpx. Závislosti `requirements-api.txt`.

**Hotovo když:** `python -m pidtools.api --port 8765 --token X` běží a testy kostry jsou v CI.

### M7 · API: data a signály
- Nahrání souboru a odhad sloupců (CSV, Excel), mapování rolí, rozsahy.
- Signály binárně: časy Float64, hodnoty Float32, jako dnešní prohlížeč záznamu.
- Kvalita dat, události v záznamu, detekce MAN / AUTO.

**Hotovo když:** 1 mil. vzorků se načte a přenese do 2 s (test výkonu).

### M8 · API: projekt
- Uložení a načtení projektu (s daty i bez), migrace starých verzí, export stavu.

**Hotovo když:** všechny projekty ze zlatých případů se načtou a znovu uloží beze změny obsahu.

### M9 · API: model (L)
- Úseky, identifikace (úloha s průběhem), dofitování se zafixovanými parametry, struktury poruch, porovnání,
  křížové ověření, nejistota, kontroly věrohodnosti, data pro grafy (model × data, rezidua).

**Hotovo když:** výsledky přes API souhlasí se zlatými případy.

### M10 · API: ladění a simulace (L)
- Blok PIDConL a sady, metody a návrh, kontroly, porovnání metod, scénář (simulace), dopředná vazba, robustnost
  (nejistota modelu), frekvenční analýza (Bode, Nyquist, S/T).

**Hotovo když:** souhlas se zlatými případy.

### M11 · API: ostatní (L)
- APC (všechny techniky), diagnostika, přehled smyček, report (HTML, beze změny `app.report`), OPC UA (jen čtení).

**Hotovo když:** souhlas se zlatými případy. Report z API je shodný s dnešním (porovnání HTML bez časových značek).

---

## Fáze C – nový frontend (`frontend/`, TypeScript)

Výchozí volba (R1): **React + Vite + TypeScript**, Zustand, TanStack Query, uPlot pro XY grafy. Pro testy Vitest
a Playwright.

### M12 · Kostra frontendu
- `frontend/` s lintem (ESLint), typy generovanými z `openapi.json` a Vitest. CI pro frontend (build, typy, testy).
- Design tokeny (CSS proměnné z dnešního návrhu), světlé a tmavé téma, fonty z M2, texty z M3.
- Shell:
  - hlavička se záložkami;
  - panel nastavení vpravo;
  - stavový řádek;
  - průběh úloh se zrušením.
- FastAPI servíruje sestavené UI. Dev režim přes Vite proxy.

**Hotovo když:** v prohlížeči je prázdná aplikace se záložkami, přepnutím jazyka a tématu a Playwright smoke test.

### M13 · Data
- Načtení souboru, mapování sloupců, rozsahy, kvalita dat.
- `viewer.js` a `viewer_an.js` převedené na TS moduly beze změny chování: Node testy zůstávají, rozložení se ukládá
  do projektu.

**Hotovo když:** e2e scénář dnešního testu prohlížeče projde v novém UI.

### M14 · Model 1 (L)
- Úseky: společný i podle vstupů. Komponenta `trend.js` převedená na TS s táhly.
- Vyřazení dat, režim dat (automaticky, otevřená, uzavřená smyčka, Ručně / AUTO po úsecích).
- Identifikace s průběhem, tabulka výsledků a výběr modelu.

### M15 · Model 2 (L)
- Karty přenosů (MV i poruchy), ruční úpravy, zafixování a dofitování, porovnání struktur.
- Validace a rezidua, křížové ověření, nejistota, varování (MAN / AUTO, θ ≈ 0, Set 1).

**Hotovo když (M14 + M15):** zlaté případy modelu vyjdou v novém UI stejně (e2e).

### M16 · Ladění 1
- Blok PIDConL (parametry, rozsahy, SampleTime), sady 1–3, metody a návrh, kontroly věrohodnosti.

### M17 · Ladění 2 (L)
- Porovnání metod, scénář (SP, porucha, šum, omezení), KPI.
- Dopředná vazba, Smith, robustnost, frekvenční analýza.

### M18 · Živá simulace
- `live_engine.js` a `live_ui.js` převedené do TS. Test shody s `core/simulation.py` zůstává.

### M19 · APC (L)
- Všechny dnešní techniky, včetně „vrátit na vypočtené“.

### M20 · Diagnostika a Přehled smyček

### M21 · Projekt, report, OPC UA
- Uložení a načtení projektu (soubor), report (náhled a stažení), čtení z OPC UA.

**Hotovo když (M16–M21):** pro každou záložku projde e2e scénář převzatý z dnešních AppTest a desktop testů.

---

## Fáze D – nasazení

### M22 · Sidecar
- PyInstaller „onedir“ z `pidtools.api` (Python, numpy, scipy, bez Qt a Streamlitu), se spuštěním
  `--port --token --parent-pid`. Ukončí se se zavřeným oknem.
- Smoke test zabaleného programu v CI na Windows.

**Hotovo když:** zabalený backend nastartuje do 4 s a projde smoke testem.

### M23 · Okno desktopu (Tauri)
- Tauri 2:
  - spustí sidecar na volném portu s náhodným tokenem;
  - zobrazí UI;
  - otevírá a ukládá soubory přes systémové dialogy.
- Jedna instance aplikace, otevření projektu poklepáním (asociace přípony).

### M24 · Instalátor a release
- NSIS instalátor pro uživatele bez admin práv. MSI pro správce (tichá instalace).
- Varianty s WebView2 bootstrapperem a s pevným runtime pro uzavřené sítě.
- Podpis Authenticode (R4). Release workflow na tag; dnešní `offline-package.yml` se nahradí.

### M25 · Offline ověření
Kontrolní seznam na čistém Windows 10 a 11 bez sítě:
- instalace;
- start;
- všechny záložky;
- uložení projektu;
- odinstalace.

K tomu kontrola, že aplikace nedělá žádné síťové požadavky mimo `127.0.0.1`.

### M26 · Web pro tým
- Jeden kontejner (API + statické UI).
- Přihlášení (R3): Cloudflare Access nebo OIDC.
- Pracovní prostor na uživatele, limity velikosti souborů a počtu úloh, vypršení nečinnosti, logy.
- Návod v `docs/deployment.md`.

---

## Fáze E – přechod

### M27 · Parita a pilot
- Kontrolní seznam funkcí stará × nová aplikace a zlaté případy v obou.
- Pilot u 2–3 uživatelů na reálných projektech, oprava rozdílů.

### M28 · Vypnutí staré aplikace
- Odstranit `pidtools/ui` (Streamlit) a `pidtools/desktop` (PySide6) i jejich testy a závislosti.
- Aktualizovat dokumentaci a příručku (nové snímky). Vydat **verzi 4.0**.

---

## Rozhodnutí

| | Otázka | Výchozí volba | Potřeba nejpozději před |
|---|---|---|---|
| R1 | Frontend | React + TypeScript | M12 |
| R2 | Obal desktopu | Tauri 2 (záloha Electron) | M23 |
| R3 | Přihlášení na webu | Cloudflare Access | M26 |
| R4 | Podpis instalátoru | firemní certifikát, standardní (EV jen pokud trvá SmartScreen) | M24 |
| R5 | Zmrazení staré aplikace | desktop PySide6: jen opravy hned; Streamlit: jen opravy od M14 | M14 |
| R6 | Cílová PC | Windows 10 / 11, instalace uživatelem, část bez internetu | M24 |

Dokud rozhodnutí nepadne, platí výchozí volba.

## Odhad
Celkem ≈ 40–55 sezení:
- fáze A ≈ 8–10;
- fáze B ≈ 10–12;
- fáze C ≈ 16–22;
- fáze D ≈ 6–8;
- fáze E ≈ 3.

Po fázi A je dnešní aplikace čistší a testovanější, i kdyby se další fáze odložily. Po fázi B lze API použít
i samostatně (skripty, napojení na jiné systémy).
