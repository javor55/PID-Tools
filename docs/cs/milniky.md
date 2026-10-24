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
| M1 | Zlaté případy | A | M | – | ☑ |
| M2 | Přibalené fonty (offline) | A | S | – | ☑ |
| M3 | Texty CZ / EN do JSON | A | S | – | ☑ |
| M4 | Pracovní prostor v `app` (stav bez UI) | A | L | M1 | ☑ |
| M5 | Úlohy s průběhem a zrušením, cache | A | M | M4 | ☑ |
| M6 | Kostra API (FastAPI, token, OpenAPI) | B | M | M4 | ☑ |
| M7 | API: data a signály | B | M | M6 | ☑ |
| M8 | API: projekt | B | S | M6 | ☑ |
| M9 | API: model | B | L | M5, M7 | ☑ |
| M10 | API: ladění, scénář, robustnost, frekvence | B | L | M9 | ☑ |
| M11 | API: APC, diagnostika, přehled smyček, report, OPC UA | B | L | M10 | ◐ |
| M12 | Kostra frontendu (TS, design, téma, jazyk) | C | M | M3, M6, **R1** | ◐ |
| M13 | Záložka Data + prohlížeč záznamu | C | M | M7, M12 | ◐ |
| M14 | Model 1: úseky, identifikace, výsledky | C | L | M9, M13 | ◐ |
| M15 | Model 2: karty přenosů, úpravy, validace, nejistota | C | L | M14 | ◐ |
| M16 | Ladění 1: blok PIDConL, sady, návrh, kontroly | C | M | M10, M15 | ◐ |
| M17 | Ladění 2: porovnání, scénář, robustnost, frekvence | C | L | M16 | ◐ |
| M18 | Živá simulace | C | M | M16 | ☑ |
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

**Skutečnost:**
- 2 050 klíčů v `pidtools/i18n/cs.json` a `en.json`; desktop build JSON přibaluje.
- `tests/test_i18n.py` kontroluje shodu klíčů a zástupných hodnot, platný formát a JSON.
- **Pro M12:** pět textů používá formát Pythonu (`{tc:.4g}`, `{r:.0f}`, `{ts:g}`). Formátovač v TS musí umět `.Nf`,
  `.Ng` a `g`.

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

**Skutečnost (M4a–d naráz):** Desktopový stav byl už bez Qt, takže se přesunul celý.
- `pidtools/app/workspace/`:
  - `Workspace` složený z částí `data` (M4a), `ident` (M4b), `tuning` (M4c), `analysis` a `project` (M4d);
  - `loops.Project` – víc smyček nad jedním souborem.
- Desktop (`state.LoopState`, `project.Project`) je jen alias.
- Diagnostika (KPI, ventil, hystereze, nelinearita) se přesunula z okna desktopu do `analysis`.
- Zlaté případy běží přes `Workspace`.
- **Zbývá na později:** web dál drží stav v `st.session_state` a nad workspace přejde až s novým UI. Přestavba
  stránek Streamlitu by se nevyplatila, nahradí je M12–M21. APC návrhy (technika po technice) jsou dál v
  `app.apc` volané z oken; obal ve workspace dostanou s API (M11).

### M5 · Úlohy a cache
- `pidtools/app/jobs.py`: dlouhé výpočty (identifikace, optimalizace ladění, nejistota, APC) v procesech, s průběhem
  (0–100 % a text), zrušením a časovým limitem.
- Cache výsledků podle klíče vstupů (logika z `ui/cache.py`) s limitem paměti.

**Hotovo když:** úlohu jde zrušit do 1 s a výsledek z cache se vrátí bez přepočtu (test).

**Skutečnost:**
- `pidtools/app/jobs.py`:
  - `JobManager` – každá úloha běží ve vlastním procesu („spawn“); fronta s limitem souběžných úloh; průběh
    (podíl a text); zrušení a časový limit ukončením procesu; hotové úlohy se po čase zapomenou.
  - `ResultCache` – LRU s limitem velikosti.
- `tests/test_jobs.py`:
  - výsledek, průběh a chyba;
  - zrušení do 1 s a časový limit;
  - fronta s limitem;
  - cache: výsledek bez přepočtu; skutečná identifikace na demu.
- Dnešní web a desktop zůstávají u svých cache (`st.cache_data`, vlákno v desktopu). JobManager použije API (M6).

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

**Skutečnost:**
- `pidtools/api`: `create_app()`, `store.WorkspaceStore` (vypršení, limit počtu), `__main__` (bez `--token` se
  token vygeneruje a vypíše na první řádek).
- Endpointy:
  - `/health`, `/i18n/{lang}`;
  - `/workspaces` – vytvořit, stav, smazat;
  - `/jobs/{id}` – stav, `cancel`, `events` (SSE).
- `pidtools/api/openapi.json` hlídá test. Závislosti jsou v `requirements-api.txt` (FastAPI 0.161, uvicorn 0.50).
- `tests/test_api.py`: token, CORS jen pro okno aplikace, vypršení prostorů, SSE průběh, zrušení, spuštění
  z příkazové řádky na 127.0.0.1.

### M7 · API: data a signály
- Nahrání souboru a odhad sloupců (CSV, Excel), mapování rolí, rozsahy.
- Signály binárně: časy Float64, hodnoty Float32, jako dnešní prohlížeč záznamu.
- Kvalita dat, události v záznamu, detekce MAN / AUTO.

**Hotovo když:** 1 mil. vzorků se načte a přenese do 2 s (test výkonu).

**Skutečnost:**
- `pidtools/api/data.py`, endpointy pod `/workspaces/{id}`:
  - `data/demo`, `data/file` (tělo = soubor, `?name=` určí formát);
  - `layout`, `columns`, `range`, `settings` (GET a PATCH, jen klíče projektu);
  - `signals` – binárně; `raw` = ze souboru, `grid` = převzorkované pv / mv / sp / d0… / valid;
  - `quality`, `loopmode`, `compression`.
- Binární formát (`app.signalpack`) sdílí API s prohlížečem záznamu ve Streamlitu:
  `[uint32 délka][popis JSON][Float64 časy][Float32 hodnoty]`.
- Výkon: CSV s 1 mil. řádků se dřív parsovalo dvakrát (desetinná tečka i čárka). Teď rozhodne vzorek a čte se
  jednou: 3,3 s → 0,6 s; s převzorkováním ≈ 1 s. Přenos 2 signálů po 1 mil. vzorků (15 MB) trvá 0,3–0,7 s.

### M8 · API: projekt
- Uložení a načtení projektu (s daty i bez), migrace starých verzí, export stavu.

**Hotovo když:** všechny projekty ze zlatých případů se načtou a znovu uloží beze změny obsahu.

**Skutečnost:**
- Pracovní prostor API drží celý projekt (`workspace.loops.Project`); data a výpočty jdou na aktivní smyčku.
- `pidtools/api/projects.py`:
  - `GET/PUT /project` – s daty i bez, starší verze s migrací; projekt bez dat použije načtená data;
  - `/loops` – seznam, přidání (zadané nebo odhadnuté sloupce), aktivní smyčka, odebrání.
- `tests/test_api_project.py`: TIC001 i formát v1 se přes API vrátí beze změny; ověřeny i smyčky a projekt bez dat.

### M9 · API: model (L)
- Úseky, identifikace (úloha s průběhem), dofitování se zafixovanými parametry, struktury poruch, porovnání,
  křížové ověření, nejistota, kontroly věrohodnosti, data pro grafy (model × data, rezidua).

**Hotovo když:** výsledky přes API souhlasí se zlatými případy.

**Skutečnost:**
- `pidtools/api/model.py`:
  - `windows` – úseky, vyřazení dat; `windows/mode` – ručně / AUTO;
  - `identify` – úloha;
  - `model` – výsledky s FIT na aktuálních úsecích, NRMSE, hodnocením, kontrolami, křížovým ověřením a nejistotou;
  - `model/select`, `model/reset`; úlohy `model/refit`, `model/crossval`, `model/uncertainty`;
  - `model/curves` – binárně: model, jen MV, jen poruchy, celý záznam, rezidua.
- Výpočty běží jako úlohy na odlehčené kopii prostoru (`Workspace.lean`, ≈ 150 kB) a výsledek se zapíše zpět.
  Opakovaná identifikace se stejnými vstupy jde z cache.
- `tests/test_api_model.py`: modely demo i TIC001 (kombinovaná) přes API = zlaté případy; ověřeny i dofitování
  se zafixovaným θ, nejistota, křížové ověření, průběhy a zastaralý model.

### M10 · API: ladění a simulace (L)
- Blok PIDConL a sady, metody a návrh, kontroly, porovnání metod, scénář (simulace), dopředná vazba, robustnost
  (nejistota modelu), frekvenční analýza (Bode, Nyquist, S/T).

**Hotovo když:** souhlas se zlatými případy.

**Skutečnost:**
- `pidtools/api/tuning.py`:
  - `tuning` – metody, sady s robustností, doporučení D, historie;
  - `tuning/suggest` – návrh s upozorněními a kontrolami;
  - `tuning/sets/{n}` – zápis sady s historií;
  - `tuning/compare` – úloha; výsledek na `/jobs/{id}/result`;
  - `scenario` – předvolby, vlastní události, SP z → na;
  - `simulate` – ukazatele; `simulate/curves` – binárně v inženýrských jednotkách;
  - `frequency` – L, S, T, Ms, GM, PM, šířka pásma.
- `tests/test_api_tuning.py`: návrhy všech metod, robustnost Set 1, scénář (Set 1 i návrh) a frekvence přes API
  = zlatý případ demo.
- Dopředná vazba (FF) a Smith mají vlastní endpointy od M11b (`apc/ff`, `apc/smith`).

### M11 · API: ostatní (L)
- APC (všechny techniky), diagnostika, přehled smyček, report (HTML, beze změny `app.report`), OPC UA (jen čtení).

**Hotovo když:** souhlas se zlatými případy. Report z API je shodný s dnešním (porovnání HTML bez časových značek).

**Skutečnost – M11a (hotovo):**
- `pidtools/api/analysis.py`:
  - `diagnostics` – KPI, ventil, hystereze, nelinearita (= zlatý případ);
  - `apc/recommend` – doporučené struktury;
  - `report` – protokol HTML, stejná funkce jako desktop.
- `pidtools/api/opcua.py`: `opc/browse`, `opc/find`, `workspaces/{id}/opc/history` (úloha → data prostoru),
  test proti lokálnímu testovacímu serveru.
- Jazyk textů z výpočtů (doporučení, protokol) podle `?lang=` nebo `Accept-Language`.
- Přehled smyček = `/loops` (M8).

**Skutečnost – M11b (část):**
- `pidtools/api/apc.py` (tag `apc`), výpočty beze změny z `app.feedforward`, `app.apc.feedforward`, `app.apc.smith`.
- Dopředná vazba:
  - `GET apc/ff` – po měřených poruchách nastavení {use, dyn, gain, lead, lag, delay} (zesílení v % MV na jednotku
    poruchy, k tomu `eng_gain` v jednotkách MV), návrh podle modelu, příznak ručních úprav, výchozí skok a hodnoty
    pro PIDConL (zapnuté poruchy);
  - `PUT apc/ff` – seznam částečných změn po pořadí (`null` = beze změny) → `ws.ff_state` (`ffm.state`), stejně jako
    desktop; čte ho i ladění (`set_ctrl`, simulace, scénář);
  - `POST apc/ff/reset` – `{index}` (bez indexu všechny): zesílení, lead, lag a zpoždění znovu z modelu;
  - `POST apc/ff/simulate` – skok poruchy bez FF / statická / dynamická (sada 2): IAE a max. odchylka PV;
    `apc/ff/simulate/curves` – průběhy binárně v inženýrských jednotkách. Simulace trvá ≈ 0,05 s, proto synchronně.
- Smithův prediktor:
  - `GET apc/smith` – vstupy z nastavení (stejné klíče jako desktop a web: `apc_sm_method`, `apc_sm_ct`,
    `apc_sm_tc|…`, `apc_sm_man`, `apc_sm_ek` / `et` / `eth`; mění se přes `PATCH /settings`), regulátor, poměr θ,
    pracovní bod, `basis_text`, `general_rows`, `values` a řádky pro šablonu (u integračního procesu jen regulátor);
  - `POST apc/smith/simulate` (`ek`, `et`, `eth` [%], jinak z nastavení) – IAE (SP, porucha) PID vs. Smith;
    `apc/smith/simulate/curves` – průběhy binárně;
  - `POST apc/smith/optimize` – robustní optimalizace jako úloha (≈ 2 s na demu); výsledek se drží u prostoru
    a vrací ho `GET apc/smith` (`opt_ready`); simulace s metodou OPT bez výsledku odpoví 409.
- `tests/test_api_apc.py`: výchozí návrh FF = `ffm.design`, zápis a čtení, reset, vliv FF na simulaci ladění,
  simulace FF a Smith = přímá volání `app.apc.*`, hodnoty šablony, ruční metoda přes nastavení, optimalizace (úloha).

**Zbývá – M11b:** ostatní techniky APC (kaskáda, rozvazbení, override, gain scheduling, poměr, split range, VPC)
jako endpointy nad `app.apc.*`; každá má vlastní vstupy a výsledky.

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

**Skutečnost:**
- `frontend/`:
  - React 19, TypeScript 5.9, Vite 8, Zustand, TanStack Query; ESLint, Vitest;
  - npm 11 (`packageManager`; npm 10 padá na peer závislostech vitestu);
  - verze balíčků staré aspoň 2 týdny, přesně zafixované.
- Typy z `openapi.json` (`npm run api-types`); CI hlídá, že odpovídají.
- Shell:
  - hlavička s 8 záložkami (texty z `/i18n`), jazyk CS / EN, vzhled světlý / tmavý / podle systému;
  - panel nastavení, stavový řádek se spojením a úlohami (průběh a zrušení).
- Klient API: token z adresy (`#token=`) nebo od desktopu; jazyk v `Accept-Language`; SSE přes fetch.
- Formát textů jako Python `str.format` (`{x:.4g}`, `{x:.0f}`) – testováno na hodnotách z Pythonu.
- Design tokeny z dnešního webu; fonty z `/fonts`.
- API servíruje sestavené UI na `/` (`pidtools/api/ui`, mimo git; staví CI).
- Testy: `tests/test_frontend.py` (Playwright) ověřuje záložky, jazyk, vzhled, spojení, prostor, žádný externí
  požadavek a fonty; Vitest pro formát.

### M13 · Data
- Načtení souboru, mapování sloupců, rozsahy, kvalita dat.
- `viewer.js` a `viewer_an.js` převedené na TS moduly beze změny chování: Node testy zůstávají, rozložení se ukládá
  do projektu.

**Hotovo když:** e2e scénář dnešního testu prohlížeče projde v novém UI.

**Skutečnost:**
- Prohlížeč záznamu je jeden sdílený modul pro oba weby: `pidtools/ui/static/viewer.js`, `viewer_an.js` a nově
  `viewer.css`. Nový web ho připojí adaptérem `RecordViewer`.
- Chování se tím nemění. Převod do TS má smysl až po vypnutí Streamlitu (M28), do té doby by to byla dvojí údržba.
- Adaptér:
  - stáhne binární data z `/signals` a vloží je do mezipaměti prohlížeče;
  - doplní role a barvy signálů smyčky a texty `vw_*`;
  - rozložení ukládá do nastavení `dview`, tedy i do projektu.
- Panel záložky:
  - zdroj: ukázka, nebo soubor nahraný do API;
  - sloupce PV / MV / SP / poruchy / poloha;
  - kvalita dat a podíl MAN / AUTO.
- Zbývá:
  - rozložení tabulky (dlouhý formát / dvojice čas–hodnota, formát času, ruční perioda);
  - OPC UA dialog;
  - jednotky a rozsahy.
  Endpointy už existují (`/layout`, `/opc/*`, `/settings`).
- `tests/test_frontend.py`: stejný scénář jako dnešní test prohlížeče (panely, signály, kurzory, zoom tabulky),
  navíc kvalita, MAN / AUTO, změna sloupce SP, uložené rozložení a nahrání souboru.

### M14 · Model 1 (L)
- Úseky: společný i podle vstupů. Komponenta `trend.js` převedená na TS s táhly.
- Vyřazení dat, režim dat (automaticky, otevřená, uzavřená smyčka, Ručně / AUTO po úsecích).
- Identifikace s průběhem, tabulka výsledků a výběr modelu.

**Skutečnost:**
- Graf s úseky je sdílený modul obou webů (`trend.js`, nově `trend.css`) přes adaptér `Trend`. Řádky (PV s modelem
  a rezidui, MV a poruchy s úseky, vyřazená data) skládá TS stejně jako `wincharts.py`.
- Úseky se mění táhly a přepínač společný / podle vstupů se ukládá do API.
- Panel:
  - data pro identifikaci (automaticky / otevřená / uzavřená smyčka) s podílem MAN / AUTO;
  - upozornění na nevyplněný Set 1;
  - režim úseků MV ručně / AUTO;
  - modely, θ max, neměřené poruchy, znaménko, stikce;
  - tlačítko Identifikovat (úloha s průběhem ve stavovém řádku).
- Tabulka modelů: FIT na aktuálních úsecích, NRMSE, hodnocení, parametry, výběr modelu, kontroly věrohodnosti.
- Nastavení a výběr modelu se v UI mění hned a s API se sjednotí potom.
- `/model/curves` vrací průběhy v inženýrských jednotkách, kontroly modelu nesou i hodnoty.
- Test v prohlížeči: identifikace dema přes nové UI = zlatý případ (I1D), výběr modelu, průběh modelu v grafu,
  přepnutí režimu úseků.

### M15 · Model 2 (L)
- Karty přenosů (MV i poruchy), ruční úpravy, zafixování a dofitování, porovnání struktur.
- Validace a rezidua, křížové ověření, nejistota, varování (MAN / AUTO, θ ≈ 0, Set 1).

**Hotovo když (M14 + M15):** zlaté případy modelu vyjdou v novém UI stejně (e2e).

**Skutečnost M15:**
- Parametry vybraného modelu (procesu i poruch podle struktury) lze ručně upravit a zafixovat. K tomu dofitování
  a návrat k nafitovaným hodnotám.
- Ověření modelu: FIT, NRMSE, R², bělost reziduí ACF / CCF, hodnocení.
- Křížové ověření (úseky podle vstupů), nejistota (bootstrap, 5 % / 95 %), upozornění k modelům.
- API: názvy parametrů a struktury poruch u výsledků, `/model/validation`.
- Test v prohlížeči: zafixované θ = 30 s po dofitování, nejistota se 3 variantami.
- **Zbývá:** porovnání struktur poruch (výběr jiné struktury z porovnání), grafy reziduí a ACF.

### M16 · Ladění 1
- Blok PIDConL (parametry, rozsahy, SampleTime), sady 1–3, metody a návrh, kontroly věrohodnosti.

**Skutečnost M16:**
- Sady 1 / 2 s robustností (Ms, GM, PM). Návrh zvolenou metodou s poznámkami a kontrolami věrohodnosti
  (zesílení smyčky, rozdíl proti Set 1, zpoždění ≈ 0); zápis návrhu do Set 2 / Set 1 s historií.
- Odezva scénáře pro Set 1, Set 2 a návrh (PV, MV) s ukazateli: IAE, překmit, doba do 90 %, ustálení.
- Panel: blok PIDConL (SampleTime, DiffGain, NormPV / NormMV, meze MV, PropFacSP, D ve zpětné vazbě), prvky
  smyčky (deadband, filtr PV, rychlost MV, rampa SP), nastavení metod (typ regulátoru, kritérium, cíl, překmit,
  Ms, robustnost).
- Nové sdílené prvky: `LineChart` (SVG) a nastavovací pole navázaná na klíče projektu.
- Test v prohlížeči: návrh SIMC = API, zápis do Set 2, odezva a ukazatele, změna SampleTime.

### M17 · Ladění 2 (L)
- Porovnání metod, scénář (SP, porucha, šum, omezení), KPI.
- Dopředná vazba, Smith, robustnost, frekvenční analýza.

**Skutečnost M17 (část):**
- Porovnání všech metod (úloha `/tuning/compare`, průběh ve stavovém řádku): tabulka Gain, TI, TD, Ms, IAE
  poruchy a SP, překmit, šum MV; kliknutí na řádek převezme parametry jako návrh (odezva, ukazatele, frekvence).
- Scénář: předvolba, SP z → na, amplitudy poruch předvoleb, editor událostí (zapnuto, kam působí, typ,
  amplituda, začátek, konec, perioda, setrvačnost; přidat / smazat). Úprava řádku předvolby z ní udělá vlastní
  scénář (stejně jako desktop).
- Frekvenční analýza pro Set 1, Set 2 a návrh: tabulka (stabilita, Ms, GM, PM, ωc, šířka pásma), Bodeho
  diagram (amplituda, fáze) a citlivost |S| / |T|.
- Nyquistův diagram L pro Set 1, Set 2 a návrh: kružnice Ms, kritický bod −1, pohled Re, Im ∈ [−3; 1,5].
- Simulace s rozptylem modelu (`spread`): přepínač v záložce Ladění, dostupný po výpočtu nejistoty (záložka Model);
  varianty jsou šedé čáry v grafu PV.
- Test v prohlížeči: předvolba a vlastní událost (= API), frekvence (včetně Nyquista), porovnání metod a převzetí řádku.
- Zbývá: dopředná vazba a Smith (chybí API – přidat v M11b), simulace s robustností (`robust`).

### M18 · Živá simulace
- `live_engine.js` a `live_ui.js` převedené do TS. Test shody s `core/simulation.py` zůstává.

**Skutečnost M18:**
- `live_engine.js` a `live_ui.js` se nepřepisují do TS: nové rozhraní je používá beze změny chování jako prohlížeč
  záznamu (`LiveTab.tsx`, typy v `legacy.d.ts`); test shody s `core/simulation.py` (`test_live_js.py`) zůstává.
- Konfigurace simulace je v aplikační vrstvě (`app.live.web_config`, ze stavu prostoru `web_config_ws`); Streamlit ji
  volá také, takže obě rozhraní dostanou stejná data. Vzhled přesunut z Pythonu do `ui/static/live.css`.
- API: `GET /workspaces/{id}/live` (409 bez dat a modelu, texty v jazyce požadavku). Zápis laděného zesílení
  (trigger „apply“) jde přes existující `PUT /tuning/sets/2`.
- Záložka bez panelu nastavení (komponenta si kreslí vlastní postranní sloupec); odpojení komponenty při odchodu.
- Test v prohlížeči: start, běh času a odečet, změna zesílení a „zapsat do sady 2“ = API; test API: klíče, jazyk, 409.
- Zbývá: stav simulace se drží v prohlížeči (`window.__pidLive`), do projektu se neukládá.

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
| R1 | Frontend | **rozhodnuto: React + TypeScript** (porovnání s Vue, Svelte, Angular a Python UI – 23. 10. 2026) | M12 |
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
