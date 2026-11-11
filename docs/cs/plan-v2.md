# Plán implementace – nové UI v2 a knihovna regulátorů

Stav: **schváleno k realizaci** (11. 11. 2026).

Výchozí podklady:

- Návrh UI: artefakt „PID Tools – nový návrh UI“, verze 37: https://claude.ai/artifact/QuLnUL4JG1Y6jKfAGcmhD9. Kopie desek je v repozitáři: [docs/design/v2](../design/v2/README.md).
  Před každou etapou načíst jeho aktuální verzi.
- Technický návrh regulátorů: [regulatory.md](regulatory.md).
- Audit parity se Streamlitem: kapitola 6 tohoto dokumentu.

## 1. Co se mění oproti dnešnímu stavu

| Oblast | Dnes | Nově (návrh v37) |
|---|---|---|
| Záložky | Data · Model · Ladění · Živá · APC · Diagnostika · Přehled smyček | **Data · Model · Ladění · APC · Živá simulace**; Diagnostika a Přehled smyček jsou pod Daty |
| Data | jeden soubor, sloupce jedné smyčky | **více souborů** se společnou časovou osou, **skládání smyček** (PV, SP, MV, poloha, DV, režim, rozsahy, kaskáda), prohlížeč **Trendy** nad všemi signály |
| Diagnostika | jedna smyčka; Přehled smyček zvlášť | **Všechny smyčky s verdiktem a doporučením** (triáž) + Detail smyčky (A/B, MAN šrafovaně) |
| Hlavička | výběr smyčky | výběr se **stavem smyčky**, řádek „Pracujete na…“ v Modelu, Ladění, APC a Živé simulaci |
| Regulátor | pevně PIDConL | **knihovna regulátorů** (předvolby + vlastní), nastavení bloku podle profilu, editor, test použitelnosti |
| Ladění | metoda, scénář, sady | + τc, **Proces a ventil v simulaci**, **Export pro řídicí systém** |
| Model | identifikace, FIT celku | + validace na jiném úseku, pomocníci pro uzavřenou smyčku, nejistota |
| Živá simulace | jedna smyčka | + **zapnutí APC struktur**, poruchy DV přes přenosy modelu, rychlosti 10/50/200× (nízká priorita) |
| Projekt | report | + **Deník ladění** (neměnné snímky verzí, porovnání, obnovení), úplný report |
| Ostatní | – | **Start** (bez projektu), **Nastavení aplikace** (globální), **Průvodce** s kontrolním seznamem, „?“ u každého parametru |

## 2. Doporučené pořadí: backend nebo UI?

**Doporučení: po svislých řezech, v každém nejdřív Python a API, pak UI.** Výjimkou jsou dvě nezávislé stopy, které
mohou začít hned a běžet souběžně.

Proč nejdřív Python a API:

1. Nové obrazovky stojí na **nových datových strukturách**, které dnes neexistují: zdroje (více souborů), mapování
   smyček, profil regulátoru, snímek deníku a verdikty diagnostiky. UI postavené nad provizorními daty by se
   přepisovalo.
2. API je smlouva: `openapi.json` → typy pro frontend (`npm run gen:api`). Když je smlouva hotová a otestovaná,
   UI se dá rozdělit mezi souběžné agenty bez kolizí.
3. Výpočty musí zůstat shodné s dneškem. Zlaté testy v Pythonu je ohlídají dřív, než se cokoli změní v UI.

Proč ne všechno backend najednou: dlouho by nebylo nic vidět a chyby v návrhu API by se ukázaly pozdě. Každý řez
proto končí funkční obrazovkou.

Souběžně od začátku:

- **Stopa A – jádro regulátoru R1.** Čistě Python a JS engine, UI se nemění.
- **Stopa B – nápověda a průvodci.** Skoro jen frontend, nezávislé na datové vrstvě.

## 3. Etapy

Každá etapa = jedna až dvě session. Práce se dělí na agenty (levnější model) podle obrazovek nebo modulů,
s revizí a sloučením v hlavní session. Platí pro všechny etapy:

- Testy (`pytest`, Node, Playwright) zelené před každým push.
- Žádná změna výsledků bez záměru: zlaté případy.
- i18n CZ / EN, „?“ u každého nového pole (test pokrytí z E2).
- Aktualizovat `todo.md` a `CHANGELOG.md`.

### E1 – Jádro regulátoru R1 (backend, stopa A) · 3–4 dny · hotovo 11. 11. 2026

- `pidtools/core/controller.py`: obecný regulátor ze skládaných částí podle `regulatory.md` § 4, v kanonickém
  pořadí. Rozhraní: `init / step / track / set_tuning`, stejné jako dnešní `PIDConL`.
- PIDConL jako **profil** (`pidtools/controllers/presets/pcs7_pidconl.json`). `PIDConL` v `core.simulation`
  zůstane jako tenký obal.
- `pidtools/ui/static/ctrl_engine.js`: stejný interpret pro Živou simulaci. Test shody Python × JS na sadě signálů
  (max. odchylka < 1e-9).
- **Zlaté případy:** uložit dnešní výstupy `pidconl_sim_full`, návrhů ladění, robustnosti a živé simulace pro
  demo a 3 testovací smyčky. R1 je nesmí změnit.
- Výstup: žádná viditelná změna, všechny testy zelené, benchmark kroku.

### E2 – Nápověda a průvodci (FE + malé API, stopa B) · 3–4 dny

- `LabelHelp`, tedy viditelné „?“ s bublinou, v `NumSetting`, `SelectSetting`, `CheckSetting` a `Seg`. Připojit
  88 nezapojených klíčů nápovědy (seznam v kap. 6).
- `Md`: tabulky (průvodci „Který model / Která metoda / Která struktura kdy“).
- `GET /workspaces/{wid}/guide/{tab}` → kontrolní seznam `[{ok, text, action}]`. Dialog Průvodce podle návrhu:
  záložky Postup, Kontrolní seznam, Tabulka, Slovníček a hledání.
- APC: kontrolní seznam a implementace pro dopřednou vazbu a Smith, implementace RGA. Tlačítka akcí v
  kontrolních seznamech.
- **Test pokrytí nápovědy:** každý ovládací prvek s popiskem má „?“ nebo `title`. Kontroluje Playwright nad
  všemi záložkami.

### E3 – Datová vrstva: více zdrojů a skládání smyček (backend) · 4–5 dnů

- `app/sources.py`: seznam zdrojů. Každý zdroj má soubor (CSV / XLSX / TXT / OPC), rozvržení, časové pásmo, posun
  a vlastní vzorkování. Výstupem je **společná časová mřížka** (překryv, ruční perioda, mezery).
- `LoopSpec`: mapování rolí na `zdroj › sloupec` (PV, SP, MV, poloha, DV[], režim AUTO/MAN), rozsahy NormPV/MV,
  tag a popis, vazba kaskády. Jeden sloupec může být ve více smyčkách.
  - `Project` (dnes `app/workspace/loops.py`) drží zdroje a mapování.
  - `Workspace` čte signály přes mapování místo vlastního `df`.
- Automatický návrh smyček podle názvů tagů (`TIC101.PV / .SP / .OUT`, PCS 7 `…/PV_Out`, DeltaV `…/PV.CV`) a
  import mapování z CSV.
- **Migrace:** starý projekt = jeden zdroj + dnešní sloupce. Starý `.pidproj` se otevře beze změny výsledků
  (zlatý test).
- API:
  - `GET/POST/PATCH/DELETE /sources`
  - `GET/PUT /loops/{i}/mapping`
  - `POST /loops/suggest`
  - `GET /signals?names=…&a=&b=&n=`: zředěná data pro Trendy, statistiky a odečet kurzorů.
- Ruční perioda vzorkování (parita D1) patří sem.

### E4 – UI Data (frontend) · 5–6 dnů, 3–4 agenti souběžně

- Hlavička podle návrhu:
  - výběr smyčky seskupený podle verdiktu, se stavem
  - „+ Smyčka“ vede do Zdroje a smyčky
  - řádek „Pracujete na…“ v Modelu, Ladění, APC a Živé simulaci
  - nové pořadí záložek a podzáložky Dat
- **Zdroje a smyčky:**
  - soubory s časovou osou a společným úsekem
  - tabulka smyček s výběrem sloupců a stavem
  - panel sloupců se sparklines a přetažením
  - „Navrhnout podle názvů tagů“
- **Trendy:** strom signálů, panely (1 / na smyčku / na veličinu), kurzory A/B s odečtem, navigátor, vypočtený
  signál, export PNG/CSV, označení úseku pro Model / Diagnostiku. Rozšíření `viewer.js` / `trend.js`.
- **Kvalita dat:** dnešní obrazovka Data pro aktivní smyčku.
- Projde-li čas, sem patří i interaktivní `LineChart` (hover, zoom, pásma, export) a toasty.

### E5 – Diagnostika všech smyček (backend + UI) · 3–4 dny

- `app/triage.py`: dávková diagnostika všech smyček (využije `audit` a `diagnostics`). Výstupy:
  - podíl AUTO a výkon (Harris)
  - oscilace, stikce a hystereze, nelinearita, kvalita dat
  - společná oscilace více smyček
- **Pravidla verdiktu** s nastavitelnými prahy (Nastavení › Diagnostika). Verdikty: Ladit · Nejdřív ventil ·
  V pořádku · Nelineární → gain scheduling · Málo dat v AUTO · Kaskáda – ladit podřazenou první · Porucha z
  jiné smyčky. Každý verdikt má výpis důkazů.
- API `GET /triage` (úloha v pozadí s průběhem). Verdikty pro výběr smyčky v hlavičce.
- UI:
  - Všechny smyčky: dlaždice-filtry, „Kde začít“, tabulka, společná oscilace, detail s důkazy
  - Detail smyčky: dnešní Diagnostika + šrafování MAN, zadání θ pro Harrise (G1) a odkaz zpět

### E6 – Parita Modelu (backend + UI) · 5–7 dnů

- 4a: validace na jiném úseku (predikce / simulace smyčky se Sadou 1/2) + tabulka hodnocení (M1, M6).
- 4b: uzavřená smyčka:
  - odhad Sady 1 ze záznamu, kontrola Sady 1, malé vybuzení
  - zúžení na ruční úsek
  - CL FIT, model v otevřené smyčce (M2)
- 4c (B): odezva na skok, porovnat všechny modely, neměřená porucha, stikce S v kartě MV, odhad po úsecích,
  nejistota ±, důvody zastarání, migrace `idf|` → `fx|`.

### E7 – Regulátory R2–R5 (backend) · ~10 dní, lze dělit

- R2: formát `.pidctrl`, přepočty jednotek (zesílení / pásmo P, Ti / opakování, Kd, N / Tf …), pravidla ladění s
  přepočtem do profilu, optimalizace nad parametry profilu, robustnost numericky. API `/controllers` a profil
  smyčky (kopie v projektu).
- R3: speciální funkce:
  - mrtvé pásmo / gap, nelineární zesílení
  - anti-windup varianty, rychlostní algoritmus
  - split range / ohřev-chlazení, 3-step, PWM
  - externí reset, tracking, dynamické meze
- R4: jazyk vlastních rovnic (bezpečný, bez cyklů), překladač s chybami, oba interprety, test shody.
- R5: test použitelnosti (12 kontrol) → verdikt „Vhodný / Jen optimalizací / Nevhodný“ a protokol.
- Knihovna: globální úložiště (desktop: složka uživatele; web: prohlížeč + export/import JSON), předvolby jen ke
  čtení, „Vytvořit vlastní“ = kopie.

### E8 – UI regulátorů a Ladění (frontend) · 5–6 dnů

- Nastavení › Regulátory (knihovna, detail se záložkami), Editor (skládání + text, živá rovnice, schéma, rychlé
  kontroly), Test použitelnosti.
- Ladění:
  - karta Regulátor smyčky se Nastavením bloku podle profilu
  - parametry v jednotkách bloku
  - τc (T1), Proces a ventil (T2)
  - tabulka robustnosti, varování (T3–T5), stav FF, CSV export
  - **Export pro řídicí systém** (PCS 7 / TIA / DeltaV / CSV)

### E9 – APC a Živá simulace · 4–5 dnů (Živá = nízká priorita)

- APC: zbytky parity:
  - rozsah vnitřní PV z dat (oprava chyby)
  - popisy metod
  - jednosměrné rozvazbení
  - graf úseků gain scheduling, Ms sloupce, pásma override
  - štítky „nevhodné / není potřeba“
- Živá simulace: přepínače APC struktur pro aktivní smyčku (kaskáda, dopředná vazba, override…). Dál:
  - poruchy DV přes přenosy modelu (ruční zásah do DV za běhu)
  - rychlosti 10/50/200×, MAN/AUTO a tracking
  - stikce a charakteristika ventilu z Ladění
  - „Zapsat výsledek do deníku“

### E10 – Projekt, deník, Start, Nastavení · 4–5 dnů

- **Deník ladění.** Neměnný snímek obsahuje:
  - otisky dat (SHA-256) a data uložená v projektu
  - mapování, úseky, modely
  - profil regulátoru s verzí, nastavení bloku, metodu, scénář, výsledky, APC
  - stav (Návrh → Nasazeno → Ověřeno / Zamítnuto) s historií, autora, poznámky a přílohy

  K tomu porovnání verzí, „Otevřít tento stav“ a report z verze.
- Report: sekce Data a signály, Regulátor a blok, Scénář, Ověření v provozu (A/B z Diagnostiky), Historie změn;
  jazyk reportu; souhrnný report více smyček (audit).
- Automatické ukládání, „Nový“ projekt, Start (nedávné projekty, ukázková data).
- Nastavení aplikace (globální): jazyk, vzhled, grafy a jednotky, výška grafů, kritéria diagnostiky, výchozí
  regulátor a simulace, deník, report (logo), připojení OPC / historian, export/import nastavení.

### E11 – Nasazení · po E10

Desktop instalátor (M24), veřejný web (free tier, varianty v `nasazeni.md`), pilot (M27), vypnutí Streamlitu (M28).

### R7 – Předvolby podle manuálů · průběžně, až budou manuály

PCS 7 APL PIDConL, TIA PID_Compact / PID_Temp / PID_3Step, STEP 7 FB41 CONT_C, DeltaV PID, Honeywell Experion PID.
Každá s testem proti příkladu z dokumentace a se štítkem „ověřeno proti manuálu“.

## 4. Pořadí a závislosti

```
E1 (R1) ─────────────┐
E2 (nápověda) ───────┤ souběžně
E3 (zdroje) → E4 (UI Data) → E5 (triáž)
E6 (Model)           – nezávislé, kdykoli po E3
E1 → E7 (R2–R5) → E8 (UI regulátorů, Ladění)
E8 → E9 (APC, Živá)
E3 + E8 → E10 (deník potřebuje mapování a profil) → E11
```

**Příští session:**

1. E1 a E2 souběžně, dva agenti, plus revize. E1 je čistý backend, E2 je skoro čistý frontend.
2. Hned potom E3, aby byla připravená smlouva API pro novou záložku Data.

## 5. Rizika a rozhodnutí

- **Shoda výsledků:** E1 a E3 mění „pod kapotou“ cestu dat a regulátoru. Zlaté případy jsou podmínkou sloučení.
- **Výkon:** obecný interpret regulátoru je pomalejší než dnešní pevný kód. Cíl je < 2 µs na krok v Pythonu (jinak
  vektorizace nebo kompilace výrazu do funkce). Optimalizace volá simulaci tisíckrát.
- **Velké soubory** (historian, desítky tagů, dny při 1 s): mřížka sdílená smyčkami, zředění pro grafy na serveru,
  líné načítání sloupců.
- **Předvolby bez manuálů** zůstávají označené „neověřeno proti manuálu“.
- **Živá simulace:** rozsah držet malý (E9). Přínos je hlavně ověření celého řešení s APC a ventilem.

## 6. Audit parity se Streamlitem (11. 11. 2026)

Klasifikace 296 klíčů: 134 chybí, 90 nápověd nezapojených, 39 je jinde pod jiným klíčem, 18 zastaralých a
15 dynamických.

Musí být (A), rozdělené do etap výše:

| Kód | Co | Etapa |
|---|---|---|
| D1 | ruční perioda vzorkování | E3 |
| M1 | validace na jiném úseku | E6 |
| M2 | uzavřená smyčka | E6 |
| T1 | τc | E8 |
| T2 | proces a ventil | E8 |
| A1, A3, A5 | APC dopředná vazba, Smith, RGA – kontrolní seznam a implementace | E2 |
| U1 | tabulky v `Md` | E2 |
| U2 | kontrolní seznamy po záložkách | E2 |

Nápověda: 88 existujících klíčů je nezapojených. Týkají se:

- **Data:** rozvržení, formát času, Norm, tag
- **Model:** mix, síla poruchy, CV, nejistota, hodnocení, validace
- **Ladění:** metoda, AVG, šum OPT, scénář a události, blok, D-rada, KPI, proces a ventil
- **APC:** kaskáda, rozvazbení, override, FF, Smith, GS, GS-ER (téměř vše)
- **Diagnostika:** hystereze, θ, úsek

Vhodné (B): toasty, interaktivní grafy, výška grafů a časová jednotka, statistika a původní soubor v náhledu, CSV
export ladění, tabulka robustnosti, frekvenční sloupce a další drobnosti. Jsou rozepsané u etap E4, E6, E8 a E9.

## 7. Architektura a rozšiřitelnost (platí pro všechny etapy)

Dnešní základ zůstává. Vrstvy jsou oddělené:

- `core`: čistá numerika bez UI a bez stavu
- `app`: workflow a projekt
- `api`: FastAPI s OpenAPI, token (desktop) nebo týmový režim (web)
- `frontend`: typy generované z OpenAPI

Plán v2 tyto vrstvy nemění, jen do nich přidává. Aby aplikace zůstala rozšiřitelná a šla napojit na jiné systémy,
platí tato pravidla.

**Doménový model místo „boha“ Workspace.** Etapa E3 zavede jasné objekty v `app/domain/` (dataclasses, serializace
do JSON). `Workspace` zůstane jako fasáda pro výpočty jedné smyčky, ale stav projektu bude v doméně:

```
Project → Sources[] · Loops[ LoopSpec (mapování), Model, ControllerProfile, Tuning, Apc ] · Journal[ Snapshot ]
```

**Registry místo větvení `if`.** Rozšíření = přidat položku do registru, ne upravit kód na pěti místech:

| Registr | Příklady položek |
|---|---|
| zdroje dat | CSV, XLSX, OPC UA, později PI Web API / historian REST |
| profily regulátorů | `.pidctrl` |
| metody ladění | |
| techniky APC | |
| pravidla verdiktu diagnostiky | |
| formáty exportu | PCS 7 / TIA / DeltaV / CSV |
| sekce reportu | |

Každá položka má id, popis (i18n), schéma parametrů a test.

**Verzované formáty souborů.** `.pidproj`, `.pidctrl` a snímek deníku mají `format` a `version` a migrace
(`migrate_state` rozšířit na řetězec migrací s testy na vzorových souborech starých verzí). Snímek deníku je
neměnný a nese verzi aplikace a profilu.

**Stabilní API pro externí systémy.**

- Prefix `/api/v1` (staré cesty dočasně jako alias).
- OpenAPI publikované v repozitáři a kontrolované testem.
- Dlouhé výpočty jako úlohy (`/jobs`) s průběhem.
- Bez změn se zpětnou nekompatibilitou bez nové verze.

Díky tomu jde aplikaci volat i bez UI (skript, MES/CMMS, Jupyter, jiný nástroj).

**Python balíček jako knihovna.**

- `pidtools.core` a `pidtools.app.domain` půjdou použít přímo, např. dávková diagnostika všech smyček z noční úlohy.
- Přidat malé CLI (`python -m pidtools triage data.csv --mapping loops.csv --out report.html`).

**Integrace s řídicími systémy jen čtením a exportem.** Aplikace nezapisuje do DCS/PLC. Integrace jsou:

- čtení: OPC UA, historian, CSV
- export parametrů ve formátu pro hromadný import
- report a deník

Zápis by byl samostatný, výslovně schvalovaný modul.

**Kontroly v CI.**

- Hranice vrstev: `core` neimportuje `app` ani `api`, `app` neimportuje `api` (test importů).
- Shoda OpenAPI s typy frontendu.
- Migrace formátů.
- Zlaté případy výsledků.

Práce na tomto: E3 (doména, registr zdrojů, verze formátů, `/api/v1`), E7 (registr profilů a metod), E10 (registr
exportů a sekcí reportu, deník), CLI a dokumentace API po E5. Odhad navíc je asi 2–3 dny, rozložené do etap.

## 8. Start další session (zadání)

Spustit v prostředí **„PID-Tools“** (má povolené weby Siemens / Emerson kvůli manuálům). Větev:
`claude/vibrant-newton-uul6ny` (případně nová z `main` po sloučení). Úvodní pokyn:

> Pokračuj podle `docs/cs/plan-v2.md`: etapy E1 a E2 souběžně (agenti na levnějším modelu, já reviduji), pak E3.
> Před UI prací načti aktuální návrh (artefakt, kap. 0). Dodržuj kap. 7.

Desky návrhu pro etapy:

| Etapa | Desky |
|---|---|
| E2 | Guide |
| E4 | DataSources, DataTrends, Data |
| E5 | Overview, DataDiag |
| E6 | Main |
| E8 | Regulator, RegLibrary, RegEditor, RegTest |
| E9 | Apc, Live |
| E10 | Project, ProjectLog, Start, Settings |

### Kritéria dokončení

**E1**

- `core/controller.py` + `ctrl_engine.js` + profil `pcs7_pidconl`.
- Zlaté případy (simulace, návrhy, robustnost, živá simulace) jsou bitově nebo do 1e-9 shodné s dneškem.
- Shoda Python × JS < 1e-9.
- Krok < 2 µs.
- Celá sada testů zelená. UI beze změny.

**E2**

- Každý ovládací prvek s popiskem má „?“ (Playwright test pokrytí přes všechny záložky).
- `Md` vykreslí tabulky.
- `/guide/{tab}` + dialog Průvodce s kontrolním seznamem a akcemi.
- APC FF / Smith / RGA mají kontrolní seznam i implementaci.

**E3**

- `app/domain` (Project, Source, LoopSpec, verze formátu) a registr zdrojů.
- API `/api/v1/sources`, `/loops/{i}/mapping`, `/loops/suggest`, `/signals`.
- Společná mřížka z více souborů (posun času, ruční perioda).
- Starý `.pidproj` dává shodné výsledky.
- Test hranic vrstev.

Další etapy mají kritéria v kap. 3 (výstup každé etapy = funkční obrazovka podle desky návrhu + testy).

### Otevřené vstupy od uživatele

- Manuály DeltaV a Honeywell nahrát do `docs/manuals/` (mimo git; Siemens si stáhne session sama).
- Název hlavní záložky: zatím „Data“.
