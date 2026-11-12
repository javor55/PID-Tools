# Regulátory: knihovna rovnic a PID designer – technický návrh

Stav: návrh odsouhlasen; hotovo R1 (jádro), **R2 a R5 (backend, 12. 11. 2026)**, zbývá R3, R4, R6, R7. Vizualizace obrazovek: artefakt „PID Tools – nový návrh UI“, obrazovky
Nastavení › Regulátory, Editor regulátoru, Test použitelnosti a Ladění (výběr regulátoru).

## 1. Cíl

Dnes je regulátor v celé aplikaci napevno blok **PCS 7 APL PIDConL** (`core.simulation.PIDConL`, slovník `ctrl`
z `app.loop.block_ctrl` / `set_ctrl`). Cíl:

- popsat **libovolný průmyslový PID regulátor** – blok DCS / PLC, vlastní funkční blok, fyzický regulátor – včetně
  speciálních funkcí, které ovlivňují ladění;
- regulátor **poskládat klikáním** z předpřipravených částí, nebo **napsat jeho rovnice** v bezpečném výrazovém
  jazyce;
- **automaticky ověřit**, že je rovnice použitelná a vhodná k ladění, a určit, kterými metodami ji lze ladit;
- ladit, simulovat, počítat robustnost a psát report **v parametrech, názvech a jednotkách zvoleného regulátoru**;
- regulátory mít v **knihovně aplikace** (platí pro všechny projekty), sdílet je jako soubory a v projektu uložit
  kopii, aby se otevřel stejně i jinde.

Mimo rozsah: regulátory jiného typu než PID (MPC, fuzzy, stavové) – ty řeší APC; zápis do PLC.

## 2. Pojmy

| Pojem | Význam |
|---|---|
| **Profil regulátoru** | Úplný popis jednoho regulátoru: struktura, parametry a jednotky, speciální funkce, vstupy a výstupy, mapování pro ladění. Soubor `.pidctrl` (JSON). |
| **Předvolba** | Profil dodaný s aplikací (PCS 7 PIDConL, TIA PID_Compact …). Jen ke čtení, s ověřením proti dokumentaci výrobce. |
| **Vlastní profil** | Profil uživatele: odvozený z předvolby („Vytvořit vlastní“) nebo nový. |
| **Knihovna** | Předvolby + vlastní profily uložené v aplikaci (desktop: uživatelská složka; web: prohlížeč uživatele a export / import). |
| **Program regulátoru** | Profil přeložený do jednotného tvaru (strom výrazů), který vykonává simulace v Pythonu i v prohlížeči. |
| **Kanonický PID** | Ideální 2DOF PID `u = Kc·[b·r − y + 1/(Ti·s)·e + Td·s/(1+Td·s/N)·(c·r − y)]`, ve kterém pracují pravidla ladění. |

## 3. Architektura

```
profil (.pidctrl) ──překlad──► program (strom výrazů, JSON)
                                   │
              ┌────────────────────┼──────────────────────┐
              ▼                    ▼                      ▼
   Python: core.controller   JS: shared ctrl_engine.js   test použitelnosti
   (simulace, ladění,        (živá simulace, náhledy)    (app.controller_check)
    frekvenční analýza,
    APC, report)
```

- **Jeden program, dva interprety.** Profil – skládaný i psaný ručně – se přeloží do stejného stromu výrazů. Strom
  vykonává interpret v Pythonu (`pidtools/core/controller.py`) a v JS (`pidtools/ui/static/ctrl_engine.js`). Shodu
  hlídá test na sadě náhodných i hraničních signálů (odchylka < 1e-9), stejně jako dnes `test_live_js.py`.
- **Rozhraní regulátoru** zůstává stejné jako u `PIDConL`: `init(sp, pv, mv0, ff)`, `step(sp, pv, ff) → mv`,
  `track(...)`, `set_tuning(params)`. Všechny simulace (`pidconl_sim_full`, kaskáda, APC, živá simulace) tak dostanou
  obecný regulátor bez přepisu.
- **PIDConL se stane předvolbou.** Dnešní třída se nahradí profilem „PCS 7 APL PIDConL“; zlaté případy (`tests/golden`)
  musí dát po přechodu stejné výsledky (tolerance 1e-9). Teprve pak se stará třída odstraní.
- Profil se v projektu ukládá **jako kopie** (s kontrolním součtem a verzí), knihovna jen nabízí výběr.

## 4. Model regulátoru – skládané části

Regulátor je řetězec částí, každá s volbami a parametry. Skládání klikáním = výběr části a vyplnění voleb.
Každá volba má výchozí hodnotu „vypnuto / jako ideální PID“.

### 4.1 Signály (vstupy a výstupy)

| Signál | Směr | Popis |
|---|---|---|
| `SP`, `PV` | vstup | žádaná a měřená hodnota (inženýrské jednotky) |
| `FF[i]` | vstup | dopředné vazby (volitelně, každá se zesílením / lead-lag) |
| `TRK`, `TRK_ON` | vstup | sledování (tracking) – hodnota a povolení |
| `EXT_RESET` | vstup | externí reset / zpětné hlášení (BKCAL, „reset feedback“) |
| `MV_LO`, `MV_HI` | vstup | dynamické meze výstupu (override, kaskáda) |
| `MODE` | vstup | MAN / AUTO / CAS / TRK |
| `MV` | výstup | hlavní výstup (spojitý) |
| `MV2` | výstup | druhý výstup (ohřev / chlazení, split range) |
| `PULSE_UP`, `PULSE_DN` | výstup | krokový regulátor s motorovým pohonem (3-step) |
| `PWM` | výstup | pulzně šířková modulace (perioda, min. puls) |

Simulace vždy převádí výstup na **ekvivalentní polohu akčního členu** (u 3-step integrací přes dobu přestavení,
u PWM průměrem přes periodu), takže model procesu zůstává stejný.

### 4.2 Normování

- `% rozsahu` – PV i MV v % (PCS 7, DeltaV „% of span“, většina DCS); rozsahy z bloku (NormPV, NormMV, PV_SCALE …).
- `inženýrské jednotky` – zesílení v [jednotka MV / jednotka PV] (např. PID_Compact – ověřit).
- `vlastní` – lineární přepočet `x% = (x − lo) / (hi − lo) · 100` s libovolnými mezemi.

### 4.3 Zpracování SP a PV

- SP: meze, rampa (rychlost nahoru / dolů), filtr 1. řádu, bezrázové převzetí SP při přepnutí.
- PV: filtr 1. řádu (nebo 2. řádu), odmocnina / linearizace tabulkou, náhradní hodnota při chybě měření.

### 4.4 Regulační odchylka

- směr: přímý / nepřímý (nebo znaménko zesílení);
- **mrtvé pásmo**: žádné / nulová zóna (e = 0 uvnitř) / spojité (posunutí o šířku pásma) / **gap** se sníženým
  zesílením (koeficient uvnitř pásma) / s hysterezí;
- **nelineární zesílení**: kvadrát odchylky (`K·|e|/E0`), lineární přechod mezi dvěma zesíleními, tabulka
  zesílení podle PV / SP / MV / odchylky (gain scheduling);
- **regulační zóna** (ConZone): mimo pásmo výstup na mez.

### 4.5 Složky P, I, D a forma

- **Forma**: ideální (ISA) / paralelní (nezávislé Kp, Ki, Kd) / sériová (interaktivní, filtr D před nebo za I) /
  „učebnicová sériová s P na všech složkách“.
- **P**: na odchylce / jen na PV / váha `b` (0–1); volitelně P vypnuto.
- **I**: na odchylce; vypnuto; **anti-windup**: zastavení integrace na mezi (podmíněná integrace) / zpětný výpočet
  (back-calculation, časová konstanta Tt) / externí reset (I = filtr 1. řádu z EXT_RESET s časem Ti – DeltaV,
  Foundation Fieldbus); podržení integrace vstupem; bezrázové přepnutí.
- **D**: na odchylce / jen na PV / váha `c`; vypnuto; **filtr D**: `Td/N` (DiffGain, TdFiltRatio = 1/N) / pevná
  časová konstanta `Tf` (TM_LAG) / `α·Td` / bez filtru / filtr na celém výstupu PID.
- **Algoritmus**: polohový / rychlostní (přírůstkový – mění se chování mezí a přepínání).
- **Vzorkování**: perioda, pořadí výpočtu (P, I, D v kroku k nebo k−1), diskretizace (zpětná diference, Tustin,
  přesná pro filtry).

### 4.6 Výstup

- meze, rychlost změny (nahoru / dolů), bias, ruční hodnota;
- **split range** / ohřev–chlazení: dva výstupy, rozdělení, mezera, **různá zesílení pro každou stranu**
  (PID_Temp – koeficient chlazení);
- **3-step** (motorový pohon): doba přestavení, minimální puls a pauza, mrtvé pásmo, s / bez zpětného hlášení polohy;
- **PWM**: perioda, minimální puls;
- dopředná vazba: zesílení, lead-lag, mrtvá doba, sčítání před / za omezením.

### 4.7 Jednotky a názvy parametrů

Každý parametr má **název z faceplatu** (Gain, GAIN, K, Kp …), **jednotku** a **převod** na kanonický tvar:

| Veličina | Varianty |
|---|---|
| zesílení | K [–] · pásmo proporcionality PB [%] = 100/K · zesílení v inženýrských jednotkách |
| integrace | Ti [ms / s / min] · opakování za minutu = 60/Ti[s] · s na opakování = Ti · Ki = K/Ti |
| derivace | Td [ms / s / min] · Kd = K·Td |
| filtr D | N · 1/N · Tf · α |
| váhy | b, c [0–1] · přepínače „P na PV“, „D na PV“ |

## 5. Vlastní rovnice (ruční zápis)

Pro funkce, které skládání nepokryje, se program napíše přímo. Jazyk je záměrně malý a bezpečný:

```text
# PID s P na PV, gap pásmem a back-calculation anti-windupem
param Kp   = 1.0   "Zesílení"            [-]
param Ti   = 60    "Integrační čas"      [s]   min 0.1
param Td   = 0     "Derivační čas"       [s]
param N    = 10    "Filtr D"             [-]
param Gap  = 0.5   "Šířka gap pásma"     [%]
param Kgap = 0.3   "Zesílení v pásmu"    [-]
state I    = 0
state Df   = 0

e   = SP - PV
kg  = abs(e) < Gap ? Kgap : 1
P   = Kp * kg * (-PV)
Df  = lag(Df, Td * ddt(-PV), Td / N)
v   = P + I + Kp * Df + FF
MV  = clamp(v, MV_LO, MV_HI)
I   = I + Kp * kg / Ti * e * dt + (MV - v) * dt / Ti      # back-calculation
```

- **Deklarace**: `param` (název, výchozí hodnota, popis, jednotka, meze), `state` (stav mezi kroky s počáteční
  hodnotou nebo `init` výrazem pro bezrázový start), výstupy `MV`, volitelně `MV2`, `PULSE_UP` ….
- **Výrazy**: `+ − * / ^`, porovnání, `and or not`, podmínka `c ? a : b`; čísla a vstupy z § 4.1, `dt`, `t`.
- **Funkce**: `min max abs sign sqrt exp log clamp(x, lo, hi) deadband(x, w) gap(x, w, k) lag(stav, x, T)
  ddt(x)` (derivace zpětnou diferencí) `rate(stav, x, nahoru, dolů) lead_lag(stav, x, Tlead, Tlag)
  delay(x, T) table(x, [x…], [y…]) prev(x)`.
- **Omezení**: žádné cykly, rekurze, soubory ani síť; jeden krok výpočtu = jedno vyhodnocení programu shora dolů;
  pevný počet operací → předvídatelný čas. Překladač hlásí neznámé názvy, chybějící `MV`, použití stavu před
  deklarací a nekonzistentní jednotky.
- Skládaný regulátor se dá **zobrazit jako text** („Zobrazit rovnice“) a upravit – vznikne vlastní profil psaný
  ručně. Opačný směr (text → klikání) se nenabízí.

## 6. Ladění s obecným regulátorem

- **Mapování na kanonický PID**: profil určuje, jak se `Kc, Ti, Td, b, c, N` převedou na jeho parametry a zpět.
  U skládaných profilů se mapování odvodí samo (forma, jednotky). U ručních rovnic ho uživatel zapíše výrazy
  (např. `Kp = Kc`, `Ti = Ti/60` pro minuty) nebo ho nevyplní.
- **Pravidla** (SIMC, Lambda, AMIGO, IMC …) počítají v kanonickém tvaru a výsledek se přepočte. Když přepočet není
  přesný (sériová forma pro Ti < 4·Td, chybějící D, pevná váha), aplikace to řekne a nabídne nejbližší proveditelný
  návrh, ověřený simulací.
- **Optimalizace** pracuje přímo s parametry profilu (simulací), takže funguje i bez mapování a i pro nelineární
  regulátory (gap, nelineární zesílení, 3-step).
- **Robustnost** (Ms, GM, PM, Bode, Nyquist): u lineárních profilů z přenosu regulátoru; u ostatních z numericky
  změřené frekvenční charakteristiky (sinusové buzení malou amplitudou) s upozorněním, že platí kolem pracovního
  bodu.
- **Sada 1** (hodnoty z PLC) se zadává v parametrech profilu; pro porovnání se přepočte zpět do kanonického tvaru.

## 7. Test použitelnosti

Spustí se automaticky po každé změně profilu (rychlé kontroly) a na tlačítko (úplný test). Výsledek je seznam kontrol
se stavem ✓ / ! / ✗ a celkové hodnocení:

- **Vhodný pro ladění** (pravidla i optimalizace),
- **Jen optimalizací** (nelineární nebo bez mapování),
- **Nevhodný** – s důvodem.

| # | Kontrola | Co ověřuje |
|---|---|---|
| 1 | Překlad | syntaxe, deklarace, výstup `MV`, jednotky, meze parametrů |
| 2 | Determinismus a shoda Python / JS | stejný výstup obou interpretů na sadě signálů |
| 3 | Klid | `e = 0`, ustálené vstupy → MV se nemění (žádný drift integrace, žádné NaN) |
| 4 | Směr | kladná odchylka mění MV správným směrem podle nastavené akce |
| 5 | Ustálená odchylka | skok SP v uzavřené smyčce → nulová odchylka, má-li regulátor I složku |
| 6 | Ekvivalentní PID | odezva regulátoru v otevřené smyčce (skok e) proti kanonickému PID s mapovanými parametry; odhad ekvivalentních Kc, Ti, Td a shoda |
| 7 | Linearita | frekvenční charakteristika pro dvě amplitudy – odchylka → příznak „nelineární“ |
| 8 | Referenční procesy | uzavřená smyčka se SIMC laděním na sadě FOPDT / SOPDT / integračních procesů (setrvačné, vyvážené, s převahou zpoždění): stabilita, překmit, bez limitních cyklů mimo mrtvé pásmo |
| 9 | Anti-windup | saturace výstupu a návrat – překmit proti referenci |
| 10 | Přepínání | MAN → AUTO a tracking bez rázu |
| 11 | Numerika | různé periody vzorkování, velké signály, dělení nulou, NaN / nekonečno |
| 12 | Výkon | čas jednoho kroku – simulace celé optimalizace v rozumném čase |

## 8. Knihovna, soubory a projekt

- **Formát `.pidctrl`** (JSON, verze): identita (název, výrobce, systém, blok, verze firmwaru, zdroj dokumentace),
  struktura (§ 4) nebo program (§ 5), parametry (název, jednotka, převod, meze, výchozí hodnota), signály, mapování
  pro ladění, výsledek posledního testu, stav ověření (ověřeno proti dokumentaci / neověřeno).
- **Knihovna**: desktop – uživatelská složka aplikace; web – úložiště prohlížeče + export / import (sdílení
  souborem); později volitelně sdílená knihovna týmu na serveru.
- **Projekt** ukládá u každé smyčky kopii profilu; při otevření porovná s knihovnou a nabídne aktualizaci, nebo
  ponechání verze z projektu.
- **Výchozí profil** pro nové smyčky – volba v Nastavení › Regulátory.

## 9. Kde se to projeví v UI

- **Nastavení › Regulátory** (nové okno z hlavičky „Nastavení“): knihovna vlevo, detail vpravo v kartách Rovnice,
  Parametry a jednotky, Funkce, Vstupy a výstupy, Test; tlačítka „Vytvořit vlastní“, Import, Export, „Výchozí pro
  nové smyčky“.
- **Editor regulátoru**: přepínač **Skládání / Rovnice (text)**, vpravo živá rovnice a blokové schéma, dole
  rychlé kontroly testu.
- **Ladění**: v panelu malá karta „Regulátor smyčky“ (výběr z knihovny, stav testu, odkaz do knihovny); parametry
  sad a návrhu v názvech a jednotkách profilu; blok PIDConL nahradí karta „Nastavení regulátoru“ s volbami profilu.
- **Živá simulace, APC, report**: stejný profil; report vypíše hodnoty k zadání v názvosloví bloku.

## 10. Předvolby a ověření

Předvolby se dodají jen **ověřené proti dokumentaci výrobce** (manuál, verze, strana). Do té doby jsou v knihovně
označené „neověřeno“ a test použitelnosti to uvede.

| Předvolba | Stav |
|---|---|
| Siemens PCS 7 APL PIDConL | dnešní model – ověřit DiffGain, anti-windup proti manuálu APL |
| Siemens PCS 7 Standard Library CTRL_PID | potřeba manuál |
| Siemens STEP 7 FB41 CONT_C (+ FB42 CONT_S, FB43 PULSEGEN) | potřeba manuál |
| Siemens TIA PID_Compact, PID_Temp, PID_3Step | potřeba manuál (jednotky zesílení, anti-windup) |
| Emerson DeltaV PID (FORM Standard / Series, STRUCTURE, BETA / GAMMA) | potřeba DeltaV Books Online / white paper |
| Honeywell Experion PID (rovnice A–E, interaktivní / neinteraktivní, gap / nelineární zesílení) | potřeba manuál |
| Obecné: ISA ideální, paralelní, sériová, učebnicová | odvozeno, bez závislosti na výrobci |

## 11. Postup (fáze)

1. **R1 – jádro**: `core.controller` (skládané části § 4 v kanonickém pořadí), interpret v JS, přechod PIDConL na
   profil se shodou zlatých případů, rozhraní ve všech simulacích.
2. **R2 – profily a ladění** (hotovo, backend; optimalizace nad kanonickým PID s převodem výsledku, robustnost z
   přenosu profilu – numerické měření pro nelineární profily přijde s R3): formát `.pidctrl`, mapování a přepočty jednotek, pravidla s přepočtem, optimalizace nad
   parametry profilu, robustnost numericky, API (`/controllers`, profil smyčky).
3. **R3 – speciální funkce**: mrtvá pásma a gap, nelineární zesílení, anti-windup varianty, rychlostní algoritmus,
   split range a ohřev / chlazení, 3-step, PWM, externí reset, tracking.
4. **R4 – vlastní rovnice**: jazyk, překladač s chybovými hláškami, oba interprety, test shody.
5. **R5 – test použitelnosti** (hotovo, backend: `app/controller_check.py`, `POST /api/v1/controllers/{id}/test`;
   kontrola 2 ověřuje determinismus Pythonu, shodu s JS hlídá `test_ctrl_engine_js.py`): kontroly § 7, hodnocení, výstup do UI a reportu.
6. **R6 – UI**: Nastavení › Regulátory, editor, Ladění, Živá simulace, report; dokumentace.
7. **R7 – předvolby**: postupně podle manuálů, každá s testem proti příkladu z dokumentace.

Každá fáze má vlastní testy; R1 nesmí změnit žádný dnešní výsledek.
