# Uživatelská příručka

Příručka prochází aplikaci záložku po záložce. Každá záložka má navíc vlastního **průvodce** (📖 nahoře v záložce)
s postupem, výběrem metod a kontrolním seznamem podle stavu vašeho projektu. Pojmy vysvětluje **glosář**
v nabídce *Nápověda*.

- [Než začnete](#než-začnete) · [Horní lišta](#horní-lišta) · [1 · Data](#1--data) · [2 · Model](#2--model) ·
  [3 · Ladění PIDConL](#3--ladění-pidconl) · [4 · Živá simulace](#4--živá-simulace) · [5 · APC](#5--apc) ·
  [6 · Projekt a report](#6--projekt-a-report) · [Časté otázky](#časté-otázky)

---

## Než začnete

**Jaká data potřebujete.** Záznam smyčky s veličinami **PV** (regulovaná), **MV** (výstup regulátoru) a ideálně
**SP**. Pro identifikaci je nejlepší **skokový test v ručním režimu**: 2–4 skoky MV o 3–10 % z ustáleného stavu,
každý držet tak dlouho, až se PV ustálí (zhruba 4× časová konstanta + zpoždění). Jde to i z provozu v automatu se
skoky SP, ale model bývá méně přesný. Pokud na PV výrazně působí měřitelná porucha (přítok, teplota vstupu),
exportujte ji také.

**Vzorkování.** Perioda dat aspoň 10× kratší než časová konstanta procesu. Historian s kompresí (deadband) vytváří
„schody“ – aplikace na to upozorní; pro identifikaci si pokud možno vyžádejte nekomprimovaná data.

**Formát souboru.** CSV nebo Excel. Podporované uspořádání:

| Uspořádání | Příklad |
|---|---|
| Společný čas | `Čas;TIC101.PV;TIC101.MV;TIC101.SP` |
| Čas u každé veličiny | `Čas PV;PV;Čas MV;MV;…` (každá veličina má vlastní časy, aplikace je srovná na společnou mřížku) |
| Dlouhý formát | `Tag;Čas;Hodnota` (typický export z historianu) |

Čas může být číslo (s, min, h) nebo datum a čas v českém (`1.10.2026 14:05:00`), ISO, US či evropském formátu.
Oddělovač, desetinná čárka i kódování (UTF-8, UTF-16, windows-1250) se rozpoznají automaticky.

---

## Horní lišta

- **Projekt** – označení smyčky (tag) a načtení uloženého projektu (JSON).
- **Nápověda** – postup, glosář a informace o aplikaci.
- **Nastavení** – jazyk (čeština / angličtina) a výška grafů. Světlý / tmavý vzhled v menu ⋮ › Settings.
- **Datová lišta** – zdroj dat (**Soubor**, **Ukázka**, **Projekt**), souhrn dat (počet vzorků, perioda, rozsahy)
  a přepínač smyček.
- **Další smyčka** – přidá smyčku do projektu. Smyčky sdílejí soubor; každá má vlastní sloupce, model, ladění
  i nastavení APC. Smyčky z jednoho exportu lze spojit do kaskády, rozvazbení nebo override.

---

## 1 · Data

1. **Sloupce a jednotky** – zkontrolujte uspořádání, formát času a předvyplněné sloupce **PV, MV, SP**.
   Volitelně přidejte **měřené poruchy** a **polohu ventilu** (zpětné hlášení – pro diagnostiku ventilu).
   Doplňte jednotky PV a MV. *Rozsah regulátoru NormPV / NormMV se nastavuje v Ladění.*
2. **Náhled načtených dat** – tabulka po převzorkování, statistika a původní soubor s rozpoznanými typy.
3. **Úsek pro identifikaci** – tažením myší v grafu, posuvníkem nebo výběrem z **automaticky nalezených úseků**
   (shluky skoků MV nebo SP s hodnocením vhodnosti).
4. **Kontrola kvality dat** – počet, směr a rozestup skoků, ustálení po posledním skoku, poměr signál/šum,
   komprese historianu, vzorkování, MV na limitu, rampa SP. Každé varování říká, co s tím.
5. **Diagnostika provozu** (spodní část záložky) – na zvoleném úseku provozu:
   - **výkon smyčky**: směrodatná odchylka a IAE regulační odchylky, pohyb a reverzace MV, čas na limitu,
     Harrisův index (jak daleko je smyčka od teoretického minima rozptylu);
   - **oscilace** (perioda, pravidelnost) a **stikce ventilu** (vzájemná korelace MV–PV, fázový graf);
   - **hystereze ventilu** z polohy ventilu (je-li k dispozici);
   - **nelinearita**: lokální zesílení pro každý skok MV – když se liší víc než 1,5×, jedna sada parametrů
     nesedí všude (odkaz na gain scheduling);
   - **porovnání se druhým úsekem** – např. výkon před a po přeladění.

---

## 2 · Model

1. **Modely** – vyberte, které struktury vyzkoušet (výchozí: všechny; nejlepší podle shody se nabídne).
   Integrační modely jsou pro procesy, které se neustálí (hladina).
2. **Nastavení identifikace**:
   - *Max. θ* – horní mez dopravního zpoždění;
   - *Neměřené poruchy* – žádné / střední (filtr pomalých změn) / silné (odhad pomalé poruchy spolu s modelem);
   - *Znaménko zesílení* – automaticky / kladné / záporné (např. odtokový ventil);
   - *Identifikovat stikci* – odhad pásma stikce ventilu spolu s modelem.
3. **Identifikovat** – výsledkem je tabulka modelů (FIT, NRMSE, hodnocení, parametry) a graf model vs. data.
   Vyberte model pro ladění.
4. **Kontrola** – rezidua (měla by vypadat jako šum), porovnání všech modelů, **úprava parametrů** ručně
   s možností je zafixovat a dofitovat zbytek (např. známé zpoždění).
5. **Nejistota modelu** – bootstrap: rozptyl parametrů a odezev; použije se pro robustní ladění a rozptyl
   simulací.
6. **Ověření modelu** – model na jiném úseku dat a přehrání smyčky se Set 1 (zda simulace odpovídá tomu, jak
   smyčka skutečně běžela).

Model se ukládá ke konkrétním datům a úseku; při změně dat aplikace upozorní, že je potřeba identifikovat znovu.
Změna rozsahu regulátoru model jen přepočítá.

---

## 3 · Ladění PIDConL

1. **Blok PIDConL** – nastavte přesně jako v PCS 7:
   - **Rozsah regulátoru NormPV / NormMV** – rozsah bloku, ne rozsah dat (např. 0–300 °C). Gain je bezrozměrný
     (odchylka v % NormPV, MV v % NormMV), takže na rozsahu přímo závisí;
   - SampleTime (cyklus OB), DiffGain, PropFacSP (váha SP v P složce, 0–1), D ze zpětné vazby (DiffToFbk),
     deadband, limity MV;
   - prvky smyčky: filtr PV, rychlost MV, rampa SP.
2. **Doporučení D složky** – podle poměru zpoždění a časových konstant (PI vs. PID).
3. **Metoda** – SIMC, iSIMC, Lambda, AMIGO, průměrovací, optimalizace (viz [Metody](metody.md)).
4. **Sady parametrů** – **Set 1** = současné parametry z faceplatu (srovnání), **Set 2** = nový návrh
   (tlačítkem *Zapsat do Set 2*). Tabulka robustnosti: Ms, GM, PM, šum MV, případně nejhorší Ms přes nejistotu
   modelu.
5. **Porovnání všech metod** (rozbalovací) – všechny metody vedle sebe s Ms a IAE; výběr lze zapsat do sady.
6. **Scénář simulace** – vlastní události (skok, rampa, sinus, pulzy, šum na SP, vstup procesu, PV nebo měřenou
   poruchu) nebo **přehrání naměřených poruch**. Proces a ventil v simulaci: stikce, charakteristika ventilu
   po pásmech, šum PV. Volitelně citlivost na chybu modelu, rozptyl přes nejistotu modelu a **porovnání bez
   dopředné vazby**. Tabulka ukazatelů: IAE, max. odchylka, rozsah a pohyb MV, reverzace ventilu.
7. **Stažení parametrů** (CSV).

Dopředná vazba se nastavuje v APC; v Ladění je jen stav a promítá se do všech simulací.

---

## 4 · Živá simulace

Smyčka běží přímo v prohlížeči – změny se projeví okamžitě.

- režim **Auto / Ruční**, změna SP, ruční MV, zrychlení 1–500×;
- **porovnání sad** (Set 1 vs. Set 2 současně), zápis upravených parametrů zpět do sad;
- **poruchy**: skok, rampa, sinus, náhodná, pulz – na vstupu nebo výstupu procesu;
- **měření**: šum PV a filtr;
- **změna procesu** (K, T, θ, stikce) – jak smyčka snese chybu modelu;
- ukazatele od poslední události (IAE, max. odchylka, překmit, doba ustálení, pohyb MV), délka okna,
  události v grafu, export CSV / PNG.

---

## 5 · APC

Nahoře je **doporučení** podle modelů a vazeb mezi smyčkami projektu. Každá struktura má průvodce
(*kdy použít a kdy ne, příklady, kontrolní seznam, implementace v PCS 7*), simulaci přínosu a hodnoty pro
šablony APL – viz [Implementace v PCS 7](pcs7.md).

| Struktura | Co v aplikaci uděláte |
|---|---|
| **Kaskáda** | vnitřní smyčka z jiné smyčky projektu, z dat nebo ručně; ladění vnitřní a vnější smyčky, kontrola oddělení rychlostí, simulace |
| **Dopředná vazba** | pro každou měřenou poruchu statická / dynamická FF, zesílení v jednotkách MV pro vstup FFwd, limity, simulace skoku poruchy bez FF / statická / dynamická |
| **Rozvazbení** | RGA a doporučení párování, decouplery (statické i lead-lag) z modelů křížových vazeb, simulace se změnami SP obou smyček |
| **Override** | hlavní a omezující smyčka na jednom ventilu, výběr MIN/MAX s externí zpětnou vazbou, simulace s vyznačením, kdy řídí omezení |
| **Smithův prediktor** | návrh τc, citlivost na chybu modelu (zesílení, časy, zpoždění), hodnoty do šablony SmithPredictorControl ve fyzikálních jednotkách vč. offsetu PV0 |
| **Gain scheduling** | podle **PV**: tři pracovní body z úseků dat, model a ladění v každém, tabulka pro blok GainSched, simulace na nelineárním procesu. Podle **ER**: vyšší zesílení při velké odchylce, bezpečný násobek, srovnání s řídicím pásmem ConZone |

---

## 6 · Projekt a report

- **Projekt** – uloží všechny smyčky, modely, ladění a nastavení APC, volitelně i data (soubor JSON). Načtete ho
  v horní liště *Projekt*.
- **Protokol z ladění** – zařízení, autor, stav, komentář, výběr sekcí (model, ladění, odezva, APC, podpisy);
  grafy vložené (funguje offline) nebo z internetu (menší soubor). Stáhne se jako HTML; do PDF přes *Tisk › Uložit
  jako PDF*.

---

## Časté otázky

**Musím mít skokový test?** Ne, ale je to nejlepší zdroj. Z provozu v automatu se skoky SP to jde také; z dat bez
změn (jen šum) spolehlivý model nevznikne – kontrola kvality dat to řekne.

**Kde nastavím rozsah PV?** V záložce Ladění › Blok PIDConL (NormPV / NormMV). Data zůstávají v reálných
jednotkách; rozsah určuje, jak se přepočítá Gain.

**Proč je Set 1 „nestabilní“?** Set 1 má být současné nastavení z faceplatu. Dokud obsahuje výchozí zástupné
hodnoty, aplikace vás na to upozorní.

**Mám víc smyček v jednom exportu.** Přidejte je tlačítkem *Další smyčka*; každá si vybere své sloupce.

**Ladí se regulátor jinak, když použiji dopřednou vazbu?** Ne. Dopředná vazba nemění stabilitu smyčky – regulátor
se ladí normálně a dopředná vazba se navrhuje až potom.

**Jak přenesu výsledek do PCS 7?** Tabulka parametrů v Ladění (a v protokolu) odpovídá vstupům PIDConL; hodnoty pro
šablony APC jsou v jednotlivých strukturách – viz [Implementace v PCS 7](pcs7.md).
