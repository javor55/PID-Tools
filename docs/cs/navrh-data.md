# Přestavba záložky Data – specifikace ke schválení

Stav: **schváleno, implementuje se** (viz kap. 6 Stav prací – podle ní se navazuje po přerušení). Vychází z poznámek z testování desktopové verze 4.0.0-beta.2 (listopad 2026).

## 1. Co je dnes špatně

| Problém | Kde je vidět |
|---|---|
| Smyčky (PV / SP / MV / DV) se skládají na **třech místech** | tabulka *Sources & loops*, karta *Loop signals* v *Data quality*, formulář *New loop* + panel *Loops in the file* v *Diagnostics* |
| Zdroj dat se volí na **dvou místech** | karta *Files* v *Sources & loops* a karta *Data source* (File / Demo / OPC) v *Data quality* |
| **Dva různé grafy** se stejným účelem | *Trends* (vlastní graf TrendChart: rozvržení, strom signálů, A-B kurzory) a *Data quality* (prohlížeč viewer.js: panely, Pan / Zoom X / Zoom Y, zpět / vpřed, přehled, události, tabulka, vypočtené signály) – uživatel hodnotí prohlížeč z *Data quality* jako lepší |
| Kurzory se ovládají v každém grafu jinak | *Trends*: A-B (klik / Shift+klik); *Data quality*: „Cursors“ a „Horizontal cursors“ jako dvě tlačítka s jiným chováním |
| „Use as…“ v panelu sloupců je nejasné | rozbalovací seznam u každého sloupce, nevíte, do které smyčky a role se zapíše |
| Tabulka smyček přetéká | sloupec *Range PV / MV* je při šířce 1440 px useknutý |
| *Data quality* nedává odpověď „je záznam vhodný pro ladění?“ | kontroly vhodnosti (q_*) existují v jádře, ale stránka je hlavně graf + statistika |

## 2. Cílová struktura (4 podzáložky, každá s jedním úkolem)

```
1 · Data
 ├─ Zdroje a smyčky   – CO je načtené a JAK z toho vznikají smyčky (jediné místo pro mapování)
 ├─ Trendy            – PROHLÍŽENÍ všech signálů (hlavní nástroj, prohlížeč z Data quality)
 ├─ Kvalita dat       – JE záznam aktivní smyčky VHODNÝ pro identifikaci a ladění? (verdikt, události, úseky)
 └─ Diagnostika       – JAK smyčky regulují (přehled všech + detail aktivní), bez editace smyček
```

Pravidlo: **editace smyček a zdrojů jen v „Zdroje a smyčky“**; ostatní podzáložky mapování jen zobrazují
(název smyčky, PV / MV / SP jako text) a mají odkaz *Upravit ve Zdrojích a smyčkách*.

### 2.1 Zdroje a smyčky

Hlavní plocha (shora dolů):

1. **Soubory** – beze změny funkce: přidat soubor (CSV / XLSX / TXT, přetažení), OPC UA, ukázková data,
   nastavení čtení souboru, časové pásmo / posun, odebrat. Sem se přesune vše z karty *Data source*
   (Data quality) včetně „Manual read settings“.
2. **Časové pokrytí** – beze změny (překryv / sjednocení, auto / ručně).
3. **Smyčky** – tabulka, ale **řádek = karta smyčky** ve dvou řádcích, aby nic nepřetékalo:
   - řádek 1: značka / popis · PV · SP · MV · poloha ventilu · režim
   - řádek 2: DV (štítky + přidat) · rozsahy PV a MV · kaskáda · stav (Complete / chybí PV …)
   - akce: *Navrhnout z názvů tagů*, *+ Smyčka*, *Import mapování z CSV* (beze změny).

Pravý panel **Sloupce ze souborů** – místo „Use as…“:
- u sloupce jsou vidět **štítky rolí** (např. `LIC101 · PV`), kde je sloupec použitý;
- klik na sloupec otevře malou nabídku **„Přiřadit do smyčky LIC101:“ [PV] [SP] [MV] [DV] [Poloha]**
  (smyčka = aktivní smyčka, v nabídce lze přepnout); obsazená role se ukáže s tím, co nahradí;
- přetažení sloupce do buňky tabulky zůstává.

### 2.2 Trendy (nový základ = prohlížeč z Data quality)

- Graf: **viewer.js** (panely pod sebou, Pan / Zoom X / Zoom Y, zpět / vpřed, celý rozsah, přehled s výřezem,
  události ◀⚑ ⚑▶, tabulka hodnot, CSV výřezu, vypočtené signály). Vlastní graf TrendChart se zruší.
- Z dnešních Trendů se převezme: **strom signálů** (podle smyček / podle zdrojů, jen aktivní smyčka, hledání),
  **rozvržení** (1 panel / panel na smyčku / panel na veličinu), export PNG / CSV, *Vyznačit úsek pro Model /
  Diagnostiku*.
- **Jednotné kurzory** (stejně ve všech grafech postavených na prohlížeči):
  - přepínač **Kurzory: vyp · časové (A / B) · hodnotové (Y₁ / Y₂)**;
  - klik = A (Y₁), Shift+klik = B (Y₂), tažení kurzor posune, Esc kurzory skryje;
  - **odečet pod grafem**: hodnoty všech zobrazených signálů v A, v B, Δ a mezi A–B min / max / průměr /
    směrnice (časové), resp. Y₁, Y₂, Δ (hodnotové).

### 2.3 Kvalita dat (vhodnost pro ladění aktivní smyčky)

Shora dolů:
1. **Verdikt**: *Vhodný* / *S výhradou* / *Nevhodný* pro identifikaci + seznam kontrol z jádra
   (počet a směr skoků MV / SP, odstup signálu od šumu, MV na mezi, komprese historianu, rampy SP,
   perioda vzorkování vs. dynamika, krátký konec po skoku, podíl AUTO / MAN, zamrzlé / chybějící hodnoty).
   Každá kontrola má krátké vysvětlení a u problému **co s tím** (jiný úsek, jiný soubor, test v ručním režimu).
2. **Události** (tabulka): skoky MV, změny SP, přepnutí režimu, výpadky dat – klik = graf skočí na událost.
3. **Navržené úseky pro identifikaci** (z jádra `segments.auto`): úsek, důvod, hodnocení; tlačítko
   *Použít v Modelu* nastaví úsek identifikace.
4. **Graf** aktivní smyčky (týž prohlížeč, pevné panely SP+PV / MV / DV) s vyznačenými událostmi a úseky.
5. **Statistika a jednotky** (dnešní karta, beze změny obsahu).

Odstraní se: karta *Data source* (→ Zdroje), karta *Loop signals* (→ Zdroje; zde jen text + odkaz).

### 2.4 Diagnostika

Beze změny výpočtů (*Všechny smyčky* = triáž, *Detail smyčky*). Odstraní se formulář *New loop* a panel
*Loops in the file*; tabulka smyček zůstane jen pro čtení s odkazem do Zdrojů a smyček.

## 3. Mimo záložku Data (navazuje)

- **Graf v Modelu**: zachovat úseky (uživatel je hodnotí jako výborné) a doplnit z prohlížeče **Zoom X / Zoom Y,
  zpět / vpřed a přehled s výřezem** (do sdíleného trend.js – menší riziko než přepis úseků do viewer.js).
  Model se už nyní ve výchozím stavu kreslí přes celý záznam.
- **Projekt a report jako hlavní záložka** – návrh: *6 · Projekt a report* místo tlačítka v hlavičce (viz otázka 1).

## 4. Postup (postupně, každý krok zvlášť ověřený)

| Krok | Obsah | Ověření |
|---|---|---|
| D1 | Zdroje a smyčky jako jediné místo: přesun *Data source*, karta smyčky ve 2 řádcích, nabídka přiřazení místo „Use as…“; odstranění duplicit v Data quality a Diagnostice | e2e testy mapování (výběr, přetažení, nabídka), screenshoty 1024 / 1440 px EN + CS, kontrola přetékání |
| D2 | Trendy na prohlížeči: strom signálů, rozvržení, export, úsek pro Model; jednotné kurzory a odečet | e2e kurzorů (klik, Shift, tažení, Esc, odečet), porovnání s dnešními Trendy, výkon na 20 MB souboru |
| D3 | Kvalita dat: verdikt, události, navržené úseky, *Použít v Modelu* | API test nového souhrnu (nad existujícími q_* a segments.auto), e2e skoku na událost a převzetí úseku |
| D4 | Diagnostika bez editace smyček | e2e: odkazy do Zdrojů, triáž beze změny |
| D5 | Model: zoom X / Y, zpět / vpřed, přehled v trend.js | e2e úseků (beze změny chování) + zoomu |

Každý krok: implementace → typy, lint, jednotkové a e2e testy → kontrola screenshotů (EN i CS, 1024 i 1440 px)
→ commit. Zlaté případy se nemění (jde jen o rozhraní). Práci nebudu dělit mezi agenty; pokud by některý dílčí krok
šel bokem, dostane přesné zadání a výsledek projdu řádek po řádku.

## 5. Otázky ke schválení

1. **Projekt a report**: přesunout z tlačítka v hlavičce na hlavní záložku *6 · Projekt a report*?
2. **„Use as…“**: nahradit nabídkou *Přiřadit do smyčky … [PV] [SP] [MV] [DV] [Poloha]* (bod 2.1)?
3. **Kvalita dat**: má zůstat i velký volný prohlížeč (dnešní stav), nebo stačí pevný graf aktivní smyčky
   a volné prohlížení je v Trendech?
4. **Pořadí**: D1 → D2 → D3 → D4 → D5, nebo začít D2 (Trendy / kurzory), které vás při testování nejvíc pálily?

## 6. Stav prací (pro navázání po přerušení)

Rozhodnutí z připomínek v artefaktu: Projekt a report = hlavní záložka 6; Kvalita dat jen vhodnost + jednoduchý graf
vybrané smyčky s přepínačem smyček; Trendy = hlavní prohlížení; časové A / B a hodnotové Y₁ / Y₂ kurzory nezávisle,
odečet pro oboje; vlastní panely a osa Y auto / pevná; v nabídce sloupce „+ Nová smyčka“; Diagnostika triáž + tabulka
smyček jen pro čtení; pořadí prací volím sám.

| Krok | Stav | Commit / poznámka |
|---|---|---|
| D1 Zdroje a smyčky jediné místo (nabídka přiřazení, karty smyček, demo + čtení ve Files, Kvalita / Diagnostika bez editace, analýza nad smyčkami projektu `audit/analyse {project: true}`) | hotovo | e612033 |
| D2 Sdílený graf viewer.js: kurzory A / B a Y₁ / Y₂ nezávisle (klik, Shift, Alt, Esc), odečet obojího, PNG, seznam signálů v pravém panelu (`listHost`) se skupinami (`D.groups`), společná osa stejné veličiny (`sigs[].axis`), API `me.state / setPanels / setGroups / setHost` | hotovo | tento commit |
| D3 Trendy na viewer.js (`GET /signals/all` binárně, rozvržení 1 panel / smyčka / veličina, vyznačení A–B pro Model / Diagnostiku); starý TrendChart odstraněn | hotovo | tento commit |
| D4 Kvalita dat: přepínač smyček, verdikt, kontroly, jednoduchý graf (RecordViewer `simple`), události (klik posune graf, `me.goto`), navržené úseky + „Použít v Modelu“ (`GET /dataquality/summary`) | hotovo | commit „Data quality page“ |
| D5 Diagnostika – hotovo v D1 | hotovo | |
| D6 Projekt a report jako záložka 6 (místo tlačítka v hlavičce) | hotovo | commit „Project & report as tab 6“ |
| D7 Model: zoom X / Y, zpět / vpřed, přehled v trend.js | čeká | `pidtools/ui/static/trend.js` |

Ověření každého kroku: `cd frontend && npm run lint && npm run typecheck && npm run test && npm run build`,
`ruff check pidtools tests`, `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_frontend*.py` + dotčené API testy,
screenshoty EN / CS 1024 a 1440 px.
