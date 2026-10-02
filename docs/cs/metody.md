# Metody

Přehled toho, co aplikace počítá a jak výsledky číst. Vzorce slouží k orientaci – přesné implementace jsou
v `pidtools/core/`.

- [Normování](#normování) · [Modely](#modely) · [Identifikace](#identifikace) · [Hodnocení modelu](#hodnocení-modelu) ·
  [Regulátor PIDConL](#regulátor-pidconl) · [Metody ladění](#metody-ladění) · [Optimalizace](#optimalizace) ·
  [Robustnost](#robustnost) · [Simulace](#simulace) · [Diagnostika](#diagnostika) · [Struktury APC](#struktury-apc) ·
  [Literatura](#literatura)

---

## Normování

PIDConL počítá regulační odchylku v % rozsahu **NormPV** a výstup v % rozsahu **NormMV**, proto je Gain
bezrozměrný. Aplikace pracuje uvnitř stejně: PV a MV převádí na % rozsahů regulátoru, zesílení procesu je v %/%.
Fyzikální model (např. °C na % MV) na rozsahu nezávisí – mění se jen jeho vyjádření
(K[%/%] = K[°C/%] · rozsah MV / rozsah PV). Navržený Gain ale platí jen pro zadaný rozsah, proto musí odpovídat
bloku. Při změně rozsahu aplikace model přepočítá, novou identifikaci nepotřebuje.

---

## Modely

Všechny modely mají dopravní zpoždění θ (mrtvý čas). Časy jsou v sekundách.

| Model | Přenos | Typický proces |
|---|---|---|
| 0. řád | K·e^(−θs) | velmi rychlý proces vůči vzorkování (průtok, tlak) |
| 1. řád (FOPDT) | K·e^(−θs) / (T1·s + 1) | většina samoregulačních procesů (teplota, tlak, koncentrace) |
| 2. řád (SOPDT) | K·e^(−θs) / ((T1·s + 1)(T2·s + 1)) | dvě výrazné setrvačnosti (výměník + čidlo), odezva tvaru „S“ |
| Integrační | Ki·e^(−θs) / s | hladina, poloha – proces se neustálí |
| Integrační + 1. řád | Ki·e^(−θs) / (s·(T1·s + 1)) | hladina s pomalým akčním členem nebo čidlem |

**Měřené poruchy** mají vlastní model 1. řádu se zpožděním (Kd, Tp, θd) – u integračních procesů integrační.
Zlepšují identifikaci (vliv poruchy se neplete s vlivem MV) a umožňují návrh dopředné vazby.

**Volba modelu:** nejjednodušší model s dobrou shodou. 2. řád jen tehdy, když se zřetelně zlepší shoda nebo je
odezva výrazně tvaru „S“. Integrační model pro procesy, které se při konstantním MV neustálí.

---

## Identifikace

Parametry se hledají metodou nejmenších čtverců: simulovaná odezva modelu na naměřené MV (a poruchy) se porovnává
s naměřenou PV. Dopravní zpoždění se prohledává po krocích a pak upřesňuje. Volby:

- **Neměřené poruchy**
  - *žádné* – čistá data ze skokového testu;
  - *střední* – data se před fitem filtrují horní propustí; pomalý drift se odstraní, odezvy na skoky zůstanou;
  - *silné* – pomalá neměřená porucha se odhaduje společně s modelem (vyhlazená křivka). U integračních procesů
    je oddělení poruchy od vlivu MV principiálně obtížné – lepší je poruchu měřit.
- **Znaménko zesílení** – vynucení kladného / záporného (když ho data neurčí jednoznačně).
- **Stikce ventilu** – model „stick-slip“: ventil stojí, dokud se MV nevzdálí od jeho polohy o víc než pásmo S,
  pak skočí. Pásmo S se odhaduje spolu s modelem.
- **Zafixované parametry** – známé hodnoty (např. zpoždění z délky potrubí) se zafixují, zbytek se dofituje.
- **Nejistota (bootstrap)** – identifikace se opakuje na datech s přeskládanými bloky reziduí; rozptyl parametrů ukazuje,
  jak přesně je model určen. Použije se pro robustní optimalizaci a rozptyl simulací.

---

## Hodnocení modelu

| Ukazatel | Význam |
|---|---|
| **FIT %** | 100 · (1 − ‖y − ŷ‖ / ‖y − ȳ‖); ≥ 90 výborný, 80–90 dobrý, 70–80 použitelný s opatrným laděním, < 70 raději zopakovat test nebo vybrat jiný úsek |
| **NRMSE** | odmocnina střední kvadratické chyby vztažená k rozsahu dat |
| **R²** | podíl vysvětleného rozptylu |
| **Rezidua – autokorelace** | rezidua by měla být „bílá“; výrazná autokorelace = chybějící dynamika nebo porucha |
| **Rezidua × ΔMV** | korelace reziduí se změnami MV = model nevysvětluje vliv MV (špatná struktura nebo zpoždění) |

Model vždy ověřte na **jiném úseku** dat. Dobrá shoda na identifikačním úseku sama o sobě nestačí.

---

## Regulátor PIDConL

Ideální (paralelní) tvar shodný s PIDConL:

  MV = Gain · ( e + 1/TI · ∫e dt + TD · de/dt )

- D složka je filtrovaná časovou konstantou TD / DiffGain.
- **PropFacSP** – váha žádané hodnoty v P složce jako v PIDConL: P = Gain · (PropFacSP · e − (1 − PropFacSP) · PV).
  1 = P z odchylky (standard), 0 = P jen z PV (bez rázu MV při skoku SP), mezihodnoty jsou kompromis.
  Na potlačení poruch ani stabilitu vliv nemá.
- Volitelně **D ze zpětné vazby** (DiffToFbk = 1, D jen z PV) – bez derivačního rázu při skoku SP.
- D složka bere regulační odchylku za deadbandem (DiffToFbk = 0), jako v blokovém schématu.
- Deadband (spojitý nebo skokový), limity MV s anti-windupem, omezení rychlosti MV, rampa SP, filtr PV, řídicí
  pásmo (ConZone), dopředná vazba (FFwd) a bezrázové přepínání.
- **SampleTime**: diskrétní regulátor přidává zhruba polovinu periody k dopravnímu zpoždění – návrhy s tím počítají
  (θ + SampleTime/2).

Pravidla, která navrhují regulátor v sériovém tvaru (některé PID), se přepočítávají do ideálního tvaru PIDConL.

---

## Metody ladění

Značení: K, T1, T2, θ – model (samoregulační), Ki – integrační; τc (λ) – požadovaná časová konstanta uzavřené
smyčky.

### SIMC (Skogestad 2003)
Analytická pravidla s jedním parametrem τc; výchozí τc = θ („těsná“ regulace), větší τc = pomalejší a robustnější.

- 1. řád: Gain = T1 / (K·(τc + θ)), TI = min(T1, 4·(τc + θ))
- 2. řád: PI s „pravidlem poloviny“ (T2/2 se přičte k T1 i θ), PID s TD = T2
- integrační: Gain = 1 / (Ki·(τc + θ)), TI = 4·(τc + θ)

**Kdy:** univerzální výchozí volba, dobrý kompromis rychlosti a robustnosti.

### iSIMC (Grimholt & Skogestad 2018)
SIMC s posunem o θ/3: Gain = (T1 + θ/3) / (K·(τc + θ)), TI = min(T1 + θ/3, 4·(τc + θ)), u PID TD = θ/3.
**Kdy:** samoregulační procesy s výraznějším zpožděním, kde SIMC vychází zbytečně opatrně.

### Lambda / IMC
Odezva bez překmitu s časovou konstantou λ (výchozí 3θ). TI = T1 (vykrácení pólu procesu);
u integračních procesů Gain = (2λ + θ) / (Ki·(λ + θ)²), TI = 2λ + θ.
**Kdy:** klidná a předvídatelná odezva, navazující smyčky; poruchy na vstupu dorovnává pomaleji.

### AMIGO (Åström & Hägglund 2004)
Pravidla odvozená optimalizací pro robustnost Ms ≈ 1,4, bez ladicího parametru.
**Kdy:** bezpečné první nastavení, nejistý nebo v čase proměnný proces.

### Průměrovací ladění hladiny
Co nejklidnější regulátor, který udrží hladinu v povolené odchylce ΔPV při největší změně průtoku ΔMV:
Gain = ΔMV / ΔPV, TI = 4 / (Ki·Gain).
**Kdy:** vyrovnávací nádrže – odtok má být klidný, hladina smí kolísat.

### Doporučení D složky
Podle normalizovaného zpoždění θ/(θ + T): u procesů s převládající setrvačností (malé θ/(θ+T)) PI stačí;
ve středním pásmu D složka zrychlí regulaci; u procesů s převládajícím zpožděním D nepomůže. U 2. řádu D
kompenzuje druhou časovou konstantu. D zesiluje šum – aplikace ukazuje šum MV.

---

## Optimalizace

Numerické hledání Gain, TI (a TD) přímo na modelu se **zohledněním skutečného bloku** (SampleTime, DiffGain,
PropFacSP, D ze zpětné vazby, filtr PV, rychlost MV) a vždy s podmínkou robustnosti **Ms ≤ cíl** (a Mt ≤ cíl, u PID
TD ≤ TI/4, volitelně limit šumu MV).

| Kritérium | Co minimalizuje | Kdy |
|---|---|---|
| **MIGO** | maximalizuje integrační zesílení Gain/TI = nejmenší integrál odchylky při poruše | nejlepší potlačení poruch při zaručené robustnosti; výchozí |
| **IAE** | ∫\|e\| dt | vyvážený kompromis rychlosti a tlumení |
| **ISE** | ∫e² dt | vadí hlavně velké výkyvy; razantnější regulace |
| **ITAE** | ∫t·\|e\| dt | krátké ustálení, málo dokmitávání |
| **IAE + limit překmitu** | IAE s penalizací překmitu nad limit | PV nesmí přestřelit SP |

Časová kritéria se počítají na odezvě na **poruchu**, **změnu SP**, **obojí**, nebo přímo na vašem **scénáři
simulace** (události, měřené poruchy, ventil, šum). Volba *robustně* hledá parametry, které splní Ms pro všechny
varianty modelu z nejistoty.

---

## Robustnost

| Ukazatel | Význam | Doporučení |
|---|---|---|
| **Ms** | maximum citlivostní funkce \|1/(1+L)\|; jak blízko je smyčka nestabilitě | 1,4 velmi robustní · 1,6 obvyklé · 2,0 hraniční |
| **GM** | amplitudová bezpečnost – kolikrát smí vzrůst zesílení do nestability | > 2 |
| **PM** | fázová bezpečnost | > 45° |
| **Šum MV** | směrodatná odchylka MV vyvolaná šumem PV (vysokofrekvenční zesílení regulátoru) | podle ventilu; u PID hlídat |

Ms zaručuje i minimální bezpečnosti: GM ≥ Ms/(Ms − 1) a PM ≥ 2·arcsin(1/(2·Ms)). Pro Ms = 1,6 je to GM ≥ 2,7
a PM ≥ 36°, pro Ms = 1,4 GM ≥ 3,5 a PM ≥ 42°. Pokud se proces mění víc, než tyto rezervy snesou (nelinearita),
zvolte nižší Ms nebo gain scheduling.

---

## Simulace

Simulace (dávková, kaskáda i živá) používá jediný model regulátoru PIDConL krok po kroku se všemi prvky bloku
a k tomu:

- proces podle modelu, měřené poruchy přes jejich modely;
- **ventil**: stikce (pásmo, skok), charakteristika po pásmech 10 %;
- šum PV, poruchy na vstupu i výstupu procesu, scénáře událostí;
- živá simulace v prohlížeči je port stejného výpočtu do JavaScriptu (shoda ověřená testy).

---

## Diagnostika

| Ukazatel | Metoda | Jak číst |
|---|---|---|
| **Výkon smyčky** | σ a IAE odchylky, pohyb a reverzace MV, čas na limitu | srovnání před / po přeladění |
| **Harrisův index** | minimální rozptyl z AR modelu odchylky a zpoždění | blízko 1 = na hranici možností, malý = prostor ke zlepšení |
| **Oscilace** | autokorelace (Thornhill) – perioda a pravidelnost r | r > 1 = pravidelné kmitání |
| **Stikce** | vzájemná korelace MV–PV (Horch), fázový graf | lichá korelace (ρ(0) ≈ 0) ukazuje na stikci; sudá spíš na ladění nebo vnější poruchu |
| **Hystereze ventilu** | MV vs. zpětné hlášení polohy | velikost vůle / stikce v jednotkách MV |
| **Nelinearita** | lokální zesílení pro každý skok MV vůči globálnímu modelu | poměr > 1,5 = jedna sada parametrů nesedí všude |

Kmitání způsobené stikcí přeladěním nezmizí (jen se změní perioda) – řeší se ventil, případně kaskáda na polohu.

---

## Struktury APC

### Kaskáda
Vnější regulátor zadává SP vnitřnímu. Vnitřní smyčka se naladí první (rychle, často PI nebo P); vnější smyčka
vidí uzavřenou vnitřní smyčku přibližně jako člen 1. řádu s její efektivní časovou konstantou. **Oddělení
rychlostí** aspoň 4–5× – jinak se smyčky budí. Přínos: poruchy ve vnitřní smyčce (tlak, průtok) a nelinearita
ventilu se vyřeší dřív, než se projeví na hlavní veličině.

### Dopředná vazba
Ideální člen FF = −Gporucha / Gproces = −(Kd/K) · (T·s + 1)/(Tp·s + 1) · e^−(θd − θ)·s.
**Statická** část (−Kd/K) dělá většinu práce, **dynamická** (lead-lag, zpoždění) koriguje rozdílnou rychlost.
Působí-li porucha rychleji než MV (θd < θ), ideální člen by musel předbíhat – lag se zkrátí o chybějící
předstih, při velkém rozdílu zůstane statická FF. **Regulátor se kvůli dopředné vazbě neladí jinak** – leží mimo
zpětnovazební smyčku a nemění její stabilitu; ladí se normálně a FF se navrhuje až potom. Do provozu se zavádí
se sníženým zesílením (50–80 %).

### Rozvazbení 2×2
**RGA** λ11 = K11·K22 / (K11·K22 − K12·K21) ukazuje sílu interakce a správnost párování:
λ ≈ 1 slabá interakce (rozvazbení netřeba), 0,5–0,8 nebo 1,25–2 střední, > 2 silná, < 0,5 nebo záporné =
zvažte prohození párování MV–PV. **Decoupler** je dopředná vazba z MV druhé smyčky:
D = −G12 / G11 (statický nebo lead-lag).

### Override (omezení)
Dva regulátory na jednom ventilu, výběr MIN nebo MAX: hlavní regulátor řídí normálně, omezující převezme řízení,
když jeho veličina dosáhne meze (tlak, teplota, výkon). Neaktivní regulátor sleduje skutečný výstup přes **externí
zpětnou vazbu** (external reset) – nenavíjí se a převzetí je bez rázu.

### Smithův prediktor
Regulátor vidí predikci PV bez dopravního zpoždění: PV + (model bez zpoždění − model se zpožděním)·MV. Ladí se jako
by zpoždění nebylo. Přínos hlavně při θ/(θ+T) ≳ 0,5. Je citlivý na chybu zpoždění: podhodnocené θ vede ke
kmitání, nadhodnocené se snese. Nehodí se pro integrační procesy (trvalá odchylka při trvalé poruše).

### Gain scheduling
Blok GainSched lineárně interpoluje Gain, TI a TD mezi třemi body X1 < X2 < X3; mimo body drží krajní hodnoty.
- **X = PV** – kompenzace nelineárního procesu: v každém pracovním bodě se identifikuje model a naladí regulátor
  se stejnou robustností. Ověření probíhá na nelineárním procesu složeném z modelů v bodech (zesílení podle MV,
  dynamika podle PV).
- **X = ER** (regulační odchylka) – záměrně nelineární regulátor: body −E, 0, +E; kolem SP běžné naladění,
  při velké odchylce k × Gain. Smyčka s k × Gain musí být sama robustní (aplikace hlídá Ms ≤ 2), jinak vznikne
  trvalé kmitání.
- **Řídicí pásmo ConZone** (PIDConL) – mimo pásmo MV na limit, uvnitř normální regulace. Úzké pásmo rozkmitá
  smyčku mezi limity, široké po návratu překmitne; aplikace šířku hledá simulací. Simulace předpokládá bezrázový
  návrat do regulace – ověřte chování ve své verzi APL.

---

## Literatura

- S. Skogestad: *Simple analytic rules for model reduction and PID controller tuning*, J. Process Control, 2003.
- C. Grimholt, S. Skogestad: *Optimal PI and PID control of first-order plus delay processes and evaluation of
  the original and improved SIMC rules*, J. Process Control, 2018.
- K. J. Åström, T. Hägglund: *Revisiting the Ziegler–Nichols step response method for PID control* (AMIGO),
  J. Process Control, 2004; *Advanced PID Control*, ISA, 2006.
- T. J. Harris: *Assessment of control loop performance*, Can. J. Chem. Eng., 1989.
- N. F. Thornhill a kol.: *Detection of multiple oscillations in control loops*, J. Process Control, 2003.
- A. Horch: *A simple method for detection of stiction in control valves*, Control Eng. Practice, 1999.
- E. H. Bristol: *On a new measure of interaction for multivariable process control* (RGA), IEEE TAC, 1966.
- Siemens: SIMATIC PCS 7 Advanced Process Library – dokumentace a aplikační příklady (Smith Predictor,
  entry 37361207; PID Tuning with Gain Scheduling, entry 38755162).
