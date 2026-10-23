# Plán přechodu na jedno rozhraní (TypeScript) nad Python výpočty

Stav: **schváleno k přípravě** – prováděcí plán po milnících je v [milniky.md](milniky.md). Dokument popisuje, proč a jak přejít ze dvou rozhraní (Streamlit web + PySide6 desktop)
na jedno webové rozhraní v TypeScriptu, které poběží na serveru i jako desktopová aplikace kompletně offline.
Výpočty (`pidtools/core`, `pidtools/app`) zůstávají v Pythonu beze změny.

## 0. Shrnutí

- **Doporučení:** Python backend (FastAPI) nad stávající aplikační vrstvou + jedno UI v TypeScriptu. Desktop =
  totéž UI v okně **Tauri** s přibaleným Python programem, bez internetu. Web = stejný backend a stejné UI na serveru.
- **Proč teď:** blíží se profesionální nasazení; dnešní dvojí UI (≈ 14 000 řádků) zdvojuje práci, Streamlit
  přepočítává při každém kliknutí celý skript a jeho vzhled stojí na vnitřní struktuře knihovny.
- **Pracnost:** odhadem **5–8 měsíců práce jednoho vývojáře** (s AI asistencí spíš dolní hranice), po etapách tak,
  že stará aplikace běží až do úplného nahrazení.
- **K rozhodnutí:** viz kapitola 8 (Tauri × Electron, React × Svelte, přihlašování na webu, podpis instalátoru).

## 1. Výchozí stav

| Vrstva | Obsah | Rozsah (řádky Python / JS) | Osud |
|---|---|---|---|
| `pidtools/core` | identifikace, ladění, simulace, APC, robustnost (numpy, scipy) | ≈ 2 900 | **beze změny** |
| `pidtools/app` | workflow, škálování, projekt, report, scénář, APC, kvalita dat, OPC UA | ≈ 5 000 | **beze změny**, jen tenké API nad ní |
| `pidtools/i18n` | texty CZ / EN | ≈ 2 000 klíčů | převést do JSON sdíleného s frontendem |
| `pidtools/ui` | Streamlit web | ≈ 7 100 Python + ≈ 4 000 JS | nahradit; JS komponenty převzít |
| `pidtools/desktop` | PySide6 desktop | ≈ 7 000 | nahradit |
| `tests` | jednotkové, AppTest, Node, Playwright | ≈ 3 400 | jádro a app zůstávají, UI testy přepsat |

Co dnes skřípe:
1. **Dvě rozhraní** – každá funkce se dělá dvakrát a parita se rozjíždí (prohlížeč záznamu má zatím jen web).
2. **Model Streamlitu** – každá interakce znovu spustí celý skript; výkon jsme drželi cache, línými záložkami
   a obcházením (binární data přes media endpoint, vlastní stav komponent). Stav uživatele žije v paměti serveru.
3. **Vzhled závislý na interní struktuře Streamlitu** – CSS na vnitřní třídy, verze je připnutá a hlídá ji test.
4. **Vlastní JS komponenty už dnes nesou nejnáročnější části** (graf průběhů, prohlížeč záznamu, živá simulace,
   tabulka) – Streamlit je u nich jen obal.
5. **Offline** – ~~dnešní offline balíček stahuje fonty z Google Fonts~~ (vyřešeno v M2: fonty jsou přibalené).

## 2. Cíle a požadavky

Funkční: všechny dnešní funkce (Data, Model, Ladění, Živá simulace, APC, Diagnostika, Přehled smyček, Frekvenční
analýza, Projekt a report, OPC UA), čeština a angličtina, **kompatibilní formát projektu** (otevřou se i dnešní
projekty).

Nefunkční:

| Požadavek | Cíl |
|---|---|
| Offline desktop | žádné spojení ven: fonty, skripty, ikony přibalené; žádná telemetrie, licenční server ani CDN |
| Instalace | pro uživatele bez admin práv; podepsaný instalátor; tichá instalace pro správce (MSI / parametry) |
| Odezva UI | změna parametru → graf do 100 ms tam, kde se nepočítá optimalizace; dlouhé výpočty s průběhem a zrušením |
| Web pro tým | víc souběžných uživatelů, přihlášení (SSO / Cloudflare Access), limity velikosti dat |
| Bezpečnost | desktop backend jen na `127.0.0.1` s náhodným portem a tokenem; data neopouští počítač |
| Údržba | jeden kód UI, typované rozhraní mezi Pythonem a TS kontrolované v CI |
| Aktualizace | desktop: nový instalátor (soubor), volitelně automaticky tam, kde je síť; web: kontejner |

## 3. Cílová architektura

```
 ┌──────────────── frontend (TypeScript) ────────────────┐
 │ záložky Data · Model · Ladění · Live · APC · Diag … │
 │ komponenty: trend, prohlížeč záznamu, živá simulace  │   stejný kód pro web i desktop
 │ stav: store + dotazy na API, vzorce/analýzy v JS      │
 └───────────────▲─────────────────────────▲─────────────┘
                 │ HTTP JSON + binární data │ úlohy: průběh, zrušení (SSE / WebSocket)
 ┌───────────────┴──── backend (Python, FastAPI) ────────┴┐
 │ pidtools/api: tenké endpointy, pracovní prostor (data,  │
 │ projekt), fronta dlouhých úloh (procesy)               │
 │ pidtools/app  ·  pidtools/core  ·  i18n                 │   beze změny
 └─────────────────────────────────────────────────────────┘
        desktop: Tauri okno + backend jako „sidecar“ (PyInstaller), vše lokálně
        web: kontejner (backend servíruje i statické UI) za reverzní proxy / Cloudflare
```

### 3.1 Backend (`pidtools/api`)

- **FastAPI + uvicorn**, schémata v Pydantic → **OpenAPI** → TypeScript typy generované do frontendu
  (`openapi-typescript`); CI selže, když se rozhraní rozejde.
- **Pracovní prostor** (workspace): načtený soubor, převzorkovaná data a projekt drží backend pod ID
  (desktop: jeden uživatel v paměti; web: na uživatele, s limitem a vypršením). UI posílá jen změny nastavení.
- **Endpointy** (zhruba podle `app`): načtení dat a odhad sloupců, signály (binárně, jako dnešní prohlížeč:
  časy Float64, hodnoty Float32), kvalita dat, identifikace / dofitování / porovnání struktur, návrh ladění
  a porovnání metod, simulace scénáře, robustnost a frekvenční charakteristiky, APC návrhy, diagnostika,
  projekt (uložit / načíst / migrace), report (HTML), OPC UA (jen čtení).
- **Dlouhé výpočty** (identifikace, optimalizace, nejistota) jako **úlohy** v pracovních procesech
  (`ProcessPoolExecutor`): průběh přes SSE / WebSocket, zrušení, výsledek do cache podle klíče vstupů
  (dnešní `cache.py` logika se přesune sem).
- **Report**: zůstává HTML s Plotly generované v `app.report` (beze změny).

### 3.2 Frontend

- **TypeScript + React** (doporučeno; velká základna knihoven a lidí) se store (Zustand) a dotazy na API
  (TanStack Query). Alternativa Svelte – menší a rychlejší, méně lidí na trhu.
- **Grafy**: vlastní canvas komponenty, které už máme (`trend.js`, `viewer.js`, `viewer_an.js`, `live_ui.js`,
  `live_engine.js`), převést na TS moduly; pro běžné XY grafy (Bode, Nyquist, odezvy ladění, porovnání metod)
  **uPlot** (malý, rychlý). Plotly jen v reportu.
- **Živá simulace** běží v prohlížeči jako dnes (`live_engine.js` je přepis `core/simulation.py`, shodu hlídá test).
- **Texty**: `i18n` převést do JSON (jeden zdroj pro Python report i UI).
- **Design**: dnešní návrh (karty, panel vpravo, dlaždice) jako komponenty a CSS proměnné; světlé / tmavé téma;
  fonty IBM Plex přibalené (licence OFL).

### 3.3 Desktop (offline)

- **Tauri 2**: okno s WebView2, backend jako sidecar program (PyInstaller „onedir“ – Python + numpy + scipy).
  Při startu Tauri spustí backend na náhodném portu `127.0.0.1`, předá mu jednorázový token a UI s ním mluví
  jen s tímto tokenem; po zavření okna backend skončí.
- **WebView2**: Windows 11 ho má vždy, Windows 10 obvykle. Pro uzavřené sítě varianta instalátoru s přibalenou
  pevnou verzí runtime (≈ +150 MB), pak nic nestahuje.
- **Instalátor**: NSIS / MSI z Tauri, pro uživatele bez admin práv; podpis certifikátem (Authenticode) – jinak
  SmartScreen a antiviry (zabalený Python bývá falešně hlášen).
- **Velikost**: ≈ 150–250 MB (podle přibaleného WebView2). Start ≈ 2–4 s (načtení Pythonu), pak okamžitá odezva.
- **Alternativa Electron**: Chromium v sobě (žádná závislost na WebView2), větší (≈ +100 MB) a víc paměti;
  vhodné, kdyby se WebView2 na cílových PC ukázal problémem.

### 3.4 Web

- Jeden kontejner: backend + statické UI. Za reverzní proxy (nginx / Traefik) nebo **Cloudflare Tunnel**
  (bez otevřených portů) s **Cloudflare Access** nebo firemním SSO (OIDC) pro přihlášení.
- Víc uživatelů: pracovní prostor na uživatele, limit velikosti souboru a počtu souběžných úloh, vypršení
  nečinných prostorů. Bezstavové UI → snadné škálování na víc instancí (prostor v Redis / na disku, až bude potřeba).

## 4. Co se převezme a co přepíše

| Část | Převzít | Přepsat / nové |
|---|---|---|
| `core`, `app` | celé | – |
| `i18n` | obsah | formát (JSON) |
| JS komponenty (`static/*.js`) | logika kreslení a výpočtů | obal TS modulů, rozhraní (props / události) |
| `ui/*.py`, `desktop/*.py` | rozvržení a texty jako předloha | stránky v TS |
| `ui/cache.py` | klíče a logika cache | do backendu |
| Projekt (`app.project`) | formát | načtení / uložení přes API |
| Testy core / app / Node | celé | – |
| AppTest, Playwright, desktop testy | scénáře jako předloha | e2e testy nového UI (Playwright) |
| `tools/build_*` | postup PyInstaller | build Tauri, CI release |

## 5. Postup po etapách

Každá etapa končí použitelným výsledkem; stará aplikace běží souběžně, dokud nová nepokryje vše.

| Etapa | Obsah | Odhad |
|---|---|---|
| **E0 Příprava** | rozhodnutí (kap. 8), složka `frontend/`, `pidtools/api`, CI (lint, typy, testy), generování TS typů, design tokeny, i18n do JSON, přibalené fonty | 1–2 týdny |
| **E1 API** | pracovní prostor, data a signály, projekt, identifikace, ladění, simulace, úlohy s průběhem; testy API | 2–3 týdny |
| **E2 Kostra UI + Data** | hlavička, záložky, panel nastavení, téma, jazyk; záložka Data s prohlížečem záznamu a analýzami (převzaté) | 2–3 týdny |
| **E3 Model** | úseky (podle vstupů, vyřazení dat), identifikace, karty přenosů, porovnání typů, validace, nejistota | 4–6 týdnů |
| **E4 Ladění + Živá simulace** | blok PIDConL, metody, porovnání, scénář, robustnost, frekvenční analýza; živá simulace (převzatá) | 4–6 týdnů |
| **E5 Ostatní** | APC (všechny techniky), Diagnostika, Přehled smyček, Projekt a report, OPC UA | 4–6 týdnů |
| **E6 Desktop** | Tauri, sidecar, instalátor, podpis, offline test na čistém Windows 10 / 11 bez sítě, CI release | 2–3 týdny |
| **E7 Souběh a přechod** | pilot u uživatelů, porovnání výsledků se starou aplikací (stejné projekty → stejné modely a ladění), oprava rozdílů, vypnutí Streamlitu a PySide6 | 2–4 týdny |

Celkem ≈ 21–34 týdnů (5–8 měsíců) jednoho vývojáře. Etapy E3–E5 jde dělat paralelně dvěma lidmi.

## 6. Testování a kvalita

- **Jádro a aplikační vrstva**: stávající testy beze změny – výpočty se nemění.
- **Zlaté případy**: sada projektů (demo, `suseni.csv`, APC příklady) → uložené výsledky (modely, ladění, KPI);
  API i nové UI musí dát stejná čísla jako dnešní aplikace.
- **Rozhraní API**: kontrakt z OpenAPI, testy endpointů (pytest + httpx).
- **Frontend**: jednotkové testy (Vitest), e2e (Playwright – navazuje na dnešní testy v prohlížeči), vizuální
  porovnání obrazovek.
- **Desktop**: automatický start a „smoke“ test zabaleného programu v CI (jako dnes `--smoke`), ruční offline
  test na čistém PC před vydáním.

## 7. Rizika a opatření

| Riziko | Opatření |
|---|---|
| Přepis trvá déle a stará aplikace mezitím zastará | nové funkce do staré jen opravy; nové věci rovnou jako TS moduly použitelné v obou |
| Rozdílné výsledky mezi starou a novou aplikací | zlaté případy (kap. 6), výpočty se nepřepisují |
| WebView2 chybí / je zamčený na cílových PC | varianta s pevným runtime; záloha Electron |
| Antivirus / SmartScreen blokuje instalátor | podpis certifikátem, ověření na firemních PC předem |
| Velikost a start zabaleného Pythonu | „onedir“ (rychlejší start než „onefile“), jen potřebné balíčky, líné importy (scipy) |
| Výkon u dlouhých záznamů | binární přenos signálů (už ověřené), výpočty v procesech, zrušení úloh |
| Bezpečnost lokálního backendu | jen `127.0.0.1`, náhodný port, token, CORS jen pro okno aplikace |
| Kompatibilita projektů | migrace formátu v `app.project` (už existuje), test načtení starých projektů |

## 8. Rozhodnutí k potvrzení

1. **Obal desktopu: Tauri** (doporučeno – malý, bezpečný, sidecar) **× Electron** (bez závislosti na WebView2, větší).
2. **Frontend: React** (doporučeno) **× Svelte**.
3. **Přihlášení na webu**: Cloudflare Access × firemní SSO (OIDC) × bez přihlášení jen ve vnitřní síti.
4. **Podpis instalátoru**: kdo zajistí certifikát (firma / dodavatel), EV nebo standardní.
5. **Souběh**: od kdy zmrazit nové funkce ve staré aplikaci (doporučeno: hned u desktopu PySide6, u webu od E3).
6. **Cílová PC**: Windows 10 / 11, s internetem / bez, správa (instalace správcem × uživatelem) – ovlivní
   variantu instalátoru a WebView2.

## 9. Co dělat hned (bez ohledu na rozhodnutí)

- Desktop PySide6 už nerozvíjet (jen opravy); offline potřebu pokrývá offline webový balíček.
- Nové složité části psát jako samostatné JS / TS moduly s jasným rozhraním (jako prohlížeč záznamu) – převezmou se.
- Přibalit fonty IBM Plex (dnes se stahují z Google Fonts) – pomůže i dnešnímu offline balíčku.
- Připravit zlaté případy (kap. 6) ze současné verze, dokud je jediným zdrojem pravdy.
