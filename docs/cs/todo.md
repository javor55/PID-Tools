# Úkoly

**Hlavní plán od 11. 11. 2026: [plan-v2.md](plan-v2.md)** – nové UI v2 (Data se zdroji a diagnostikou, knihovna
regulátorů, deník ladění) po etapách E1–E11. Body níže jsou zbytky sladění s návrhem v1 a jsou v plánu zařazené.

## Plán v2

- [x] **M28a – odstranění Streamlitu z `main`** (13. 11. 2026): `app.py`, Python v `pidtools/ui`, `.streamlit/`, `Dockerfile`, `start.bat`, offline balíček webu (`tools/build_offline.py`, `smoke_test.py`, job `web`), testy Streamlitu a závislost `streamlit`; zůstává `pidtools/ui/static` (sdílené JS/CSS), `plotly` a PySide6 desktop. Stará aplikace žije ve větvi `streamlit`. Zbývá M28b (desktop PySide6, verze 4.0) po pilotu.
- [x] **E10-A – Deník ladění + report** (12. 11. 2026): snímky smyčky (formát `pidtools.journal.snapshot` v1) v `journal` souboru projektu, stavy s historií, poznámky, přílohy, porovnání, „Otevřít tento stav“, report z verze, registr sekcí reportu (+ Data a signály, Regulátor a blok, Scénář, Ověření v provozu, Historie změn), jazyk reportu, souhrnný report smyček; `live_runs` převedeny do deníku. Zbývá: report z verze nemá grafy z dat (jen z uložených hodnot), A / B v reportu jen z Diagnostiky aktuální smyčky, souhrnný report bere nálezy z API (`findings`), UI je zatím nepředává z auditu / triáže; export deníku (JSON + data) z návrhu není; filtr smyčky v deníku jen podle názvu.
- [x] **E10-B – Start, globální Nastavení, autosave, Nový** (12. 11. 2026): viz změny. Nastavení aplikace na serveru (`app/appsettings.py`, `/app-settings`; výchozí regulátor a testy z `localStorage` převedeny), nový projekt / smyčka přebírá výchozí regulátor, volby simulace a prahy diagnostiky, záchranná kopie a nedávné projekty (`app/autosave.py`), Start, oddíly Nastavení, „uloženo HH:MM“ a Nový. Zbývá: jednotky a formát čísel (desetinný oddělovač, čas osy, Ti / Td v min, PB) se ukládají, ale grafy a formuláře je zatím neberou (jen výška grafů u `LineChart` bez vlastní výšky a velikost písma); autor a „poznámka povinná“ čeká na deník (E10-A), logo a firma na report (E10-A); seznam nedávných jsou kopie souborů na serveru, ne cesty `.pidproj` na disku (desktop: Rust může cesty doplnit); přepínač „Ukládat data do projektu“ musí použít tlačítko Uložit v Projektu (E10-A); složka projektů a „Průvodce při spuštění“ z návrhu zatím chybí.
- [x] **E9-B – Živá simulace** (12. 11. 2026): regulátor na `ctrl_engine.js` s profilem smyčky (shoda s `live_engine.js` < 1e-9, test `tests/test_live_js.py`), struktury sady 2 (PID / + FF / kaskáda), poruchy DV přes přenosy modelu, rychlosti 1 / 10 / 50 / 200×, „Zapsat výsledek do deníku“ do `live_runs` (zobrazeno v Projektu). Zbývá: override, Smith, split-range a ostatní struktury („brzy“ v kartě Struktura); ladění sady 2 se v kaskádě nepoužije; hook pro E10: `live_runs` v nastavení projektu převezme deník ladění; Streamlit zůstává na dřívějším jádru (bez profilu, DV a APC).
- [x] **E8-B – Ladění s profilem regulátoru** (12. 11. 2026): viz změny. Zbývá: odkaz „Otevřít v knihovně“ jen vyvolá `CustomEvent("pid:open-settings", {detail: {section: "controllers", id}})`, zapojí ho shell (E8-A); porovnání metod a živá simulace stále počítají v kanonickém PIDConL (porovnání ukazuje kanonické Kc / Ti / Td); parametry profilu bez nastavení ve smyčce (ConZone, Tf, …) se jen zobrazují; export používá názvy a jednotky profilu, přesné cesty značek TIA / DeltaV je nutné ověřit u konkrétního bloku; „stav FF“ v kartě je beze změny.
- [x] **E1 – jádro regulátoru R1** (11. 11. 2026): `core/controller.py`, profil `pcs7_pidconl`, `ctrl_engine.js`, zlaté
      případy, benchmark kroku, test hranic vrstev. Zbývá z návrhu: živá simulace v prohlížeči stále používá vlastní
      `live_engine.js` (nemá ConZone ani FF, a je sdílená se starým webem a `LiveTab.tsx`); přepnuto na `ctrl_engine.js`
      v E9-B (nový web; Streamlit zůstává na dřívějším jádru). Další části (rychlostní algoritmus, externí reset, split range,
      3-step, PWM) jsou v registrech označené jako plánované (R3).
- [x] **E7a – regulátory R2 + R5, backend** (12. 11. 2026): formát `.pidctrl` s kontrolou a migrací, knihovna (předvolby
      jen ke čtení + vlastní profily ve složce uživatele, `PIDTOOLS_CONTROLLERS_DIR`), jednotky a mapování kanonického PID
      na profil (ideální / paralelní / sériová, `controllers/units.py`, `mapping.py`), robustnost podle profilu
      (`core.robustness_for`), ladění s převodem (`app/ctl_tuning.py`), test použitelnosti 12 kontrol
      (`app/controller_check.py`), API `/controllers` a `/workspaces/{wid}/controller`, předvolby ISA (ověřené) a
      CONT_C / PID_Compact (neověřené koncepty). Zbývá: UI (E8), DeltaV / Honeywell / CTRL_PID (potřeba manuály, R7),
      optimalizace přímo nad parametry profilu a numericky měřená robustnost nelineárních profilů (s R3), shoda
      Python / JS jako kontrola 2 (hlídá `test_ctrl_engine_js.py`), volba výchozího profilu pro nové smyčky.
- [x] **E7b – regulátory R3 + R4, backend a sdílený JS** (12. 11. 2026): **R3** – registry částí v `core/controller.py` i
      `ctrl_engine.js`: gap (`deadbands.gap`), nelineární zesílení (kvadrát odchylky, tabulka podle PV / SP / MV / odchylky),
      rychlostní algoritmus (= zpětný výpočet s Tt = Ts, ověřeno nezávislou přírůstkovou implementací), externí reset
      (BKCAL, `ctl.ext_reset`), dynamické meze `set_limits`, výstupní stupně split range / 3-step (práh, min. puls a
      pauza) / PWM (min. puls, na středním výstupu); tracking = stávající `track`. Katalog částí s popisem a schématem
      parametrů (`controllers/parts.py`, `GET /controllers/parts`). R5: nelineární části → „Jen optimalizací“, robustnost
      nelineárního profilu z linearizované části s příznakem `approximate`. **R4** – jazyk vlastních rovnic
      (`controllers/program.py`: parser, kontrola s řádkem a sloupcem, strom JSON; `core/program.py`: generovaná funkce
      Pythonu, ~1 µs/krok; `ctrl_engine.js`: interpret stromu bez `eval`), `kind: "program"` v profilu, mapování `map` /
      `unmap`, `POST /controllers/compile`, kontroly R5 i pro program. Testy: `test_ctl_special.py`, `test_ctl_program.py`,
      `test_api_ctl_program.py` (shoda Python × JS < 1e-9). Zbývá: UI editoru (E8 / R6), `delay(x, T)`, hystereze,
      nelineární regulátory v optimalizaci přímo nad parametry profilu, robustnost programu jen přes mapovaný PID,
      `init` stavu neumí seznam `[…]` v `table` (řádek `state` bere `[…]` jako jednotku).
- [x] **E8-A – UI knihovny regulátorů** (12. 11. 2026): `frontend/src/settings/` – celostránkové Nastavení z hlavičky
      (tlačítko „Všechna nastavení…“ v rozbalovacím panelu; oddíly Obecné a Regulátory), **Knihovna** (skupiny Siemens /
      ostatní / Moje, hledání, štítky, záložky Rovnice · Parametry · Speciální funkce · Vstupy a výstupy · Test, Import /
      Export `.pidctrl`), **Editor** (Skládání z částí `/controllers/parts` + Rovnice (text) s číslováním řádků, značkami
      chyb z `/controllers/compile`, vkládáním úryvků, živou rovnicí, schématem, rychlými kontrolami a přepočtem návrhu
      přes `/map`) a **Test použitelnosti** (verdikt, 12 kontrol, tisk a uložení protokolu). Texty `rg_ui_*`. Testy:
      `frontend/tests/ctl.test.ts`, `tests/test_frontend_controllers.py`, pokrytí nápovědy v `test_frontend_help.py`.
      Zbývá: „Výchozí pro nové smyčky“ se pamatuje jen v prohlížeči (API volbu výchozího nemá; napojí E8-B / E10),
      výsledek testu se pamatuje jen v prohlížeči, ostatní oddíly Nastavení z návrhu (grafy, diagnostika, simulace,
      projekt, report, připojení), skládání → text je jen šablona programu (převod skladby na rovnice nemá backend),
      úprava tabulky pro `table` a mapování `map` jako formulář, upozornění na neuložené změny.
- [x] **E4-C – Data › Trendy** (12. 11. 2026): `frontend/src/tabs/data/TrendsView.tsx` + `trends/` (strom signálů podle
      smyček / zdrojů s hledáním, panely 1 / na smyčku / na veličinu, osy Y podle veličiny nebo jedna sdílená, kurzory A / B
      s odečtem a statistikou, přehledový pruh, zoom kolečkem a tažením, vypočtený signál ze vzorců `viewer_an.js`, export
      PNG / CSV viditelného okna, označení úseku A–B pro Model a Diagnostiku). Data: zředěné průběhy ze serveru
      (`/signals/trend`, min / max, okno se dotahuje po zoomu); `viewer.js` se nepoužívá (jeden záznam smyčky, vlastní
      binární balík), sdílí se jen jazyk vzorců. Nový `PUT /range/common` (úsek na společné ose → čas smyčky). Zbývá:
      „Uložit pohled“ z desky (pojmenované pohledy v projektu), vypočtené signály se neukládají do projektu (jen stav
      stránky), vypočtený signál se počítá ze zobrazených zředěných dat, jednotky signálů zdrojů se berou z názvu
      sloupce (`[°C]`) nebo role, podzáložku Trendy a mount komponent dodává E4-A.
- [x] **E5 – diagnostika všech smyček** (12. 11. 2026): `app/triage.py` (metriky smyčky: AUTO, Harris se zpožděním z modelu /
      zadaným / z dat, oscilace, stikce, hystereze, nelinearita, kvalita dat; společná oscilace ± 10 %; **registr pravidel
      verdiktu** s prahy: Ladit · Nejdřív ventil · V pořádku · Nelineární → gain scheduling · Málo dat v AUTO · Kaskáda ·
      Porucha z jiné smyčky, s důkazy), API `POST/GET /triage` (úloha na pozadí) a `GET/PUT /triage/thresholds`, UI Všechny
      smyčky (dlaždice-filtry, Kde začít, tabulka, společná oscilace, detail s důkazy, prahy v panelu), verdikty ve výběru
      smyčky v hlavičce, v Detailu smyčky zadání θ pro Harrise (G1) a odkaz zpět. Zbývá: šrafování MAN v grafu detailu,
      výsledek triáže se neukládá do projektu (jen v paměti relace), kaskáda se pozná jen podle `SP` podřazené = `MV`
      řídicí smyčky, `audit.py` označuje Harris > 0,8 jako problém (opačně než η v triáži) – sjednotit.
- [x] **E3 – datová vrstva: více zdrojů a skládání smyček** (11. 11. 2026): `app/domain` (Project, Source, LoopSpec,
      TimeGrid, verze formátu 3), registr zdrojů (CSV, TXT, XLSX, OPC), společná časová mřížka (posun, časové pásmo,
      vlastní vzorkování, překryv / sjednocení, ruční perioda, mezery), návrh smyček z názvů tagů a import mapování z CSV,
      řetěz migrací v1 → v2 → v3, `/api/v1` (staré cesty jako skrytý alias), API `/sources`, `/time-grid`,
      `/loops/{i}/mapping`, `/loops/suggest`, `/loops/import`, `/signals/trend`. Zlaté případy projdou novou cestou beze
      změny. Zbývá pro E4 (UI Data): obrazovka Trendy nad těmito endpointy (Zdroje a smyčky je hotová: `tabs/data/SourcesView.tsx`; chybí v ní náhled prvních řádků před načtením souboru, jednotky sloupců, výběr sloupců času / tagu / hodnoty ručně a odkazy „Další krok“ – ty doplní navigace podzáložek); stav smyčky (verdikt) do
      seznamu smyček přijde s E5; načtení OPC UA jako dalšího zdroje (dnes `/opc/history` nahradí projekt jedním zdrojem);
      výběr listu u XLSX; líné načítání sloupců velkých souborů (dnes se čte celá tabulka zdroje); odstranění aliasů bez
      prefixu spolu s přechodem desktopu a `sidecar.py` na `/api/v1`; `PATCH` zdroje s jinými čtecími volbami přeskládá
      smyčky, ale nafitované modely zahodí. **Kompatibilita:** projekt v3 s daty z nového UI otevře starý Streamlit bez
      dat (data jsou ve `sources`, ne v `data`); vlastní soubory v2 Streamlit ukládá i čte dál. Streamlit byl z `main`
      odstraněn (M28a); větev `streamlit` projekt v3 s daty neotevře (úkol doplnit čtení `sources` se ruší).

- **E4-A hotovo (kostra UI v2):** hlavní záložky 1 Data · 2 Model · 3 Ladění · 4 APC · 5 Živá simulace (Projekt a report je
  tlačítko v hlavičce); Data má podzáložky Zdroje a smyčky, Trendy (kostry E4-B / E4-C), Kvalita dat (dřívější Data pro
  aktivní smyčku) a Diagnostika (Všechny smyčky = dřívější Přehled smyček, Detail smyčky = dřívější Diagnostika; přepracuje
  E5). Hlavička: výběr smyčky s `<optgroup>` (Rozpracované / Bez modelu / Nekompletní mapování – jedna funkce
  `loopGroup` v `Header.tsx`, E5 doplní verdikty), stavový štítek, „+ Smyčka“ → Data › Zdroje a smyčky, souhrn „N soubory ·
  M smyček · stav z HH:MM“ (čas posledního načtení stavu, API čas uložení nemá). Řádek „Pracujete na…“ na Model / Ladění /
  APC / Živá simulace. Zbývá: toasty (volitelné), výchozí podzáložka Zdroje a smyčky až bude hotové E4-B (dnes se otevírá
  Kvalita dat), „uloženo HH:MM“ podle skutečného uložení projektu, stav smyčky z diagnostiky (E5).
- [x] **E2 – nápověda a průvodci** (11. 11. 2026): `LabelHelp` („?“ s bublinou) v polích a `Seg`, zapojené nápovědy
      (kap. 6 plánu), `Md` s tabulkami, `GET /workspaces/{wid}/guide/{tab}` + dialog Průvodce (F1, kontrolní seznam
      s akcemi, tabulky, slovníček, hledání), APC FF / Smith / RGA s kontrolním seznamem a implementací, Playwright test
      pokrytí nápovědy (všechny záložky, struktury APC a jejich varianty). Zbývá: nápovědy, které patří k funkcím, jež
      v React UI ještě nejsou (proces a ventil, ruční perioda, validace na jiném úseku, CV, kaskáda z dat – h_cas_sep /
      h_cas_t63, viewer `vw_*`), se zapojí s příslušnými etapami (E4, E6, E8, E9); kontrolní seznam „Živá simulace
      ověřena“ zůstává připomínkou (běh simulace se na serveru neeviduje).

## Sladit nové UI (React) s návrhem

Návrh: artefakt „PID Tools – nový návrh UI (všechny záložky)“, https://claude.ai/artifact/QuLnUL4JG1Y6jKfAGcmhD9
(záložky Data, Model, Ladění, Živá simulace, APC, Diagnostika, Přehled smyček, Projekt). Před začátkem načíst jeho
aktuální verzi – mohl se od 9. 10. 2026 změnit. Funkce a API zůstávají, mění se rozvržení a vzhled. Starý web
(Streamlit) už podle návrhu přestavěný je a dá se použít jako vodítko.

Zjištěno 28. 10. 2026 porovnáním snímků (návrh vs. `frontend/`):

- [x] **Hlavička** (10. 11.): smyčka, „+ Další smyčka“, souhrn dat, Projekt a report / Nastavení / „?“ (F1), záložky
      s podtržením.
- [x] **Pravý panel** (10. 11.): sbalovací karty, „Rozbalit vše / Sbalit vše“, hlavní tlačítko záložky.
- [x] **Data** (10. 11.): Zdroj dat jako přepínač, Signály smyčky s čipy DV, Statistika, Jednotky a rozsahy, Kvalita
      dat pod prohlížečem, Celý náhled s tabulkou (nové API `/dataquality`, `/datastats`, `/preview`).
- [x] **Model** (10. 11.): karty přenosů s FIT, „Identif.“, směrem účinku; Struktura modelu; štítky úseků s FIT.
- [x] **Ladění** (10. 11.): přepínač pohledů, společný graf PV + MV s kurzory Měření, Ukazatele kvality se
      zvýrazněním, karty Metoda / Návrh a sady / Scénář / Robustnost.
- [x] **APC** (10. 11.): doporučení se štítky, Průvodce v panelu, tabulka variant se zvýrazněním, Hodnoty do PCS 7.
- [x] **Diagnostika, Přehled smyček, Projekt** (10. 11.): karty podle návrhu.

Zbývá po sladění 10. 11. 2026:

- [x] **Živá simulace** (10. 11.): sdílený modul `live_ui.js` překreslen podle návrhu (lišta, graf PV / MV se
      značkami poruch a čárou „teď“, Ukazatele Sada 1 / Sada 2, karty s „?“); Streamlit má stejný vzhled.
      Rychlosti a porucha „přes model DV“ doplněny v E9-B.
- [ ] **APC:** štítky „nevhodné“ a „není potřeba“ – API vrací jen „doporučeno“ a „2. smyčka“.
      Zbývá: rychlosti 10× / 50× / 200× z návrhu, porucha „přes model DV“ (engine ji nemá).
- [x] **APC (E9-A):** štítky „nevhodné“ / „není potřeba“ (`status` v `/apc/recommend`), popisy metod, jednosměrné rozvazbení, úseky GS, Ms bodů GS, pásma override, rozsah vnitřní PV z dat (oprava).
      Zbývá: Ms sloupce u Smitha / FF (tam Ms nezávisí na variantě), pásma override v tabulce variant.
- [ ] **Diagnostika:** graf provozních dat jako jedna karta s úseky A / B (návrh), karta „Co dál“; θ pro Harrise.
- [ ] **Data:** „Zoom / Měření“ nad prohlížečem, klik v grafu Celého náhledu skočí v tabulce; ruční čtení bez
      listu / hlavičky / oddělovače (API je nemá).
- [ ] **Projekt:** Automatické ukládání, „Nový“ projekt, jazyk reportu.
- [x] **Model (E6, 12. 11.):** ověření na jiném úseku (predikce / simulace smyčky Set 1 / 2, tabulka hodnocení, verdikt), uzavřená smyčka (odhad a kontrola Set 1, hint málo buzení, zúžení na ruční úsek, CL FIT, model v otevřené smyčce), odezva na skok, porovnání modelů, stikce v kartě MV, nejistota ±, `idf|` → `fx|`.
      Zbývá: odhad zesílení po úsecích, důvody zastarání modelu, počet vyřazených vzorků; ověření simulací smyčky běží synchronně (ne jako úloha).
- [ ] Ověřit tmavý vzhled a šířku ~1000 px u všech záložek.

## Další otevřené body

Podrobně v [milniky.md](milniky.md): M24 (vydávací workflow, instalátor zatím bez podpisu), M25 (kontrolní seznam
na čistém Windows bez sítě – ruční test), M27 (pilot), M28 (vypnutí staré aplikace, verze 4.0).

## Zjištěno při E5

- [ ] **Harrisův index v Přehledu smyček (`app/audit.py`) je vyhodnocený obráceně:** jádro počítá η = σ²_MV / σ²_e
      (blízko 1 = regulace na hranici možností), ale audit hlásí jako problém η > 0,8 (`harris_hi`) a η > 0,5 (`harris`).
      Triáž (E5) bere správně nízké η jako špatné. Sjednotit (oprava změní pořadí v přehledu smyček).
- [ ] **Všechny smyčky:** sloupec Ventil ukazuje surovou hodnotu stikce („stic 0.000078“) – zobrazit v % rozsahu MV
      a s textem; šrafování MAN v grafu Detailu smyčky; uložit výsledek triáže do projektu; prahy i v Nastavení ›
      Diagnostika.
- [ ] **Řádek „Pracujete na“** ukazuje regulátor jako kanonické Kc/Ti ze Sady 1 i u jiného profilu než PIDConL – zobrazit
      název profilu a parametry v jednotkách bloku (E8).
- [ ] **Živá simulace:** štítky událostí v grafu se na začátku běhu překrývají („Struktura: kaskáda“ × „teď“) – odsadit.
- [ ] **Deník × Nastavení:** při „poznámka povinná“ API odmítne změnu stavu bez poznámky (422) – UI deníku si o poznámku
      zatím neřekne předem (jen zobrazí chybu). Logo, firma a hlavička / patička z Nastavení › Report zatím report nepoužívá.
