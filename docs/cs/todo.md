# Úkoly

**Hlavní plán od 11. 11. 2026: [plan-v2.md](plan-v2.md)** – nové UI v2 (Data se zdroji a diagnostikou, knihovna
regulátorů, deník ladění) po etapách E1–E11. Body níže jsou zbytky sladění s návrhem v1 a jsou v plánu zařazené.

## Plán v2

- [x] **E1 – jádro regulátoru R1** (11. 11. 2026): `core/controller.py`, profil `pcs7_pidconl`, `ctrl_engine.js`, zlaté
      případy, benchmark kroku, test hranic vrstev. Zbývá z návrhu: živá simulace v prohlížeči stále používá vlastní
      `live_engine.js` (nemá ConZone ani FF, a je sdílená se starým webem a `LiveTab.tsx`); přepnutí na `ctrl_engine.js`
      patří do E9 spolu s načítáním profilu v prohlížeči. Další části (rychlostní algoritmus, externí reset, split range,
      3-step, PWM) jsou v registrech označené jako plánované (R3).
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
      dat (data jsou ve `sources`, ne v `data`); vlastní soubory v2 Streamlit ukládá i čte dál. Do vypnutí Streamlitu
      (M28) případně doplnit čtení `sources` ve `ui/project.py`.

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
      Zbývá: rychlosti 10× / 50× / 200× z návrhu, porucha „přes model DV“ (engine ji nemá).
- [ ] **APC:** štítky „nevhodné“ a „není potřeba“ – API vrací jen „doporučeno“ a „2. smyčka“.
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
