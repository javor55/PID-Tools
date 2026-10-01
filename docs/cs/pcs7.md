# Implementace v PCS 7

Jak přenést výsledky z PID Tools do SIMATIC PCS 7 s knihovnou APL. Každá struktura APC má v aplikaci průvodce
s konkrétními hodnotami pro vaši smyčku – tady je přehled.

> Názvy parametrů a vstupů bloků se mohou mezi verzemi APL lišit. Ověřte je v dokumentaci své verze knihovny.
> Parametry jsou návrhem z modelu – zavádějte je postupně a ověřte na zařízení.

---

## Regulátor PIDConL

| V aplikaci | V PCS 7 | Poznámka |
|---|---|---|
| Rozsah regulátoru **NormPV / NormMV** | normovací rozsahy PV a MV bloku | musí odpovídat bloku – podle nich se přepočítává Gain |
| **Gain, TI, TD** (Set 2) | Gain, TI, TD | ideální tvar, Gain bezrozměrný; záporný Gain = opačný smysl působení |
| **DiffGain** | DiffGain (faceplate *Derivative gain*) | filtr D složky TD/DiffGain |
| **P / D ze zpětné vazby** | volby *P in feedforward path* / *D in feedback path* | P nebo D jen z PV – menší ráz MV při změně SP |
| **SampleTime** | cyklus OB, ve kterém blok běží | návrhy s ním počítají |
| **MV_LoLim / MV_HiLim** | MV_LoLim / MV_HiLim | v jednotkách MV |
| **Deadband** | DeadBand | v jednotkách PV |
| Řídicí pásmo | ConZone | jen pro gain scheduling podle ER / srovnání |
| Dopředná vazba | FFwd, FFwdHiLim, FFwdLoLim | viz níže |

**Postup:** do *Set 1* zadejte současné parametry z faceplatu, nový návrh je v *Set 2*. Tabulka parametrů
v Ladění a sekce *Parametry regulátoru PIDConL* v protokolu z ladění uvádějí původní a nové hodnoty. Parametry zapisujte ve faceplatu nebo v CFC;
změny provedené online načtěte zpět do ES, aby zůstaly v offline datech.

---

## Šablony APC (Templates › Control)

| Struktura | Šablona / bloky | Co dodá aplikace |
|---|---|---|
| **Kaskáda** | **CascadeControl** – dva PIDConL (+ ConPerMon) | Gain/TI vnitřní a vnější smyčky, kontrola oddělení rychlostí |
| **Dopředná vazba** | **FfwdDisturbCompensat** – zesílení, LeadLag, DeadTime → vstup **FFwd** | zesílení v jednotkách MV, lead, lag, zpoždění, limity FFwd |
| **Rozvazbení** | decoupler = dopředná vazba podle **FfwdDisturbCompensat**, poruchou je MV druhé smyčky | zesílení, lead-lag a zpoždění každého decoupleru |
| **Override** | **OverrideControl** – dva PIDConR, výběr **SelA02In**, external reset (**ExtReset**, **ExtResOn**) | výběr MIN/MAX, mez, parametry obou regulátorů |
| **Smithův prediktor** | **SmithPredictorControl** – Lag, Mul04, Add04 (PV0), DeadTime | LagTime, zesílení ve fyzikálních jednotkách, offset PV0, DeadTime, Gain/TI |
| **Gain scheduling** | **GainScheduling** – blok **GainSched** + PIDConL | X1…X3, Gain1…3, TI1…3, TD1…3 (podle PV nebo ER) |

### Kaskáda
1. Výstup MV vnějšího regulátoru na externí žádanou hodnotu **SP_Ext** vnitřního; rozsah MV vnějšího = rozsah PV
   vnitřního.
2. Nejdřív odlaďte a uveďte do automatu vnitřní smyčku, pak vnější.

### Dopředná vazba
1. Měřenou poruchu veďte přes zesílení, případně **LeadLag** a **DeadTime**, na vstup **FFwd** regulátoru.
   FFwd se přičítá k výstupu v **jednotkách MV** – aplikace zesílení v těchto jednotkách uvádí.
2. Posílejte **odchylku poruchy od pracovní hodnoty**, ne absolutní hodnotu – jinak MV při zapnutí skočí.
3. Omezte příspěvek limity **FFwdHiLim / FFwdLoLim**.
4. Zavádějte se zesílením 50–80 % návrhu; při chybě měření poruchy FF vypněte.

Regulátor se kvůli dopředné vazbě neladí jinak – nemění stabilitu smyčky.

### Rozvazbení
Každý decoupler je dopředná vazba z MV druhé smyčky (změna od pracovního bodu × zesílení, přes lead-lag
a zpoždění). Když je druhá smyčka v ručním režimu, decoupler vypněte.

### Override
1. Výstupy obou regulátorů do **SelA02In**, vybraná hodnota na ventil.
2. Vybranou MV veďte zpět na **ExtReset** obou regulátorů a zapněte **ExtResOn** – neaktivní regulátor se nenavíjí.
3. SP omezujícího regulátoru = mez.

### Smithův prediktor
Podle aplikačního příkladu Siemens *Smith Predictor for Control of Processes with Dead Times* (entry 37361207):
1. Vstup PIDConL.PV je v šabloně připojený na virtuální PV bez zpoždění – nepřipojujte ho na periferii.
2. Model prediktoru ve **fyzikálních jednotkách**: `SmithModelTimLag.LagTime`, `SmithModelGain.In2`,
   `SmithModelDeadti.DeadTime`. Model 2. řádu se zadá součtovou časovou konstantou.
3. Offset **PV0** (blok Add04 před DeadTime) = PV v ustáleném stavu při MV = 0; u záporného zesílení nutný.
4. Pro identifikaci smyčky, která už prediktor má, berte PV z `Pcs7AnIn.PV_Out`, ne `PIDConL.PV`.
5. Zpoždění ověřte skokem; raději ho zaokrouhlete nahoru (podhodnocené θ vede ke kmitání).

### Gain scheduling
Podle aplikačního příkladu Siemens *PID Tuning with Gain Scheduling* (entry 38755162):
1. **Podle PV:** vstup `X` je v šabloně na PV; do `X1…X3`, `Gain1…3`, `TI1…3`, `TD1…3` zadejte hodnoty
   z aplikace. PID Tuner do scheduleru parametry nenahraje – zadávají se v CFC nebo faceplatu GainSched.
2. **Podle ER:** `X` připojte na výstup `ER` regulátoru; body −E, 0, +E, `Gain1 = Gain3 = k × Gain`, TI a TD
   stejné. Ověřte bezrázovou změnu Gain a že smyčka při plném zesílení nekmitá.
3. Gain, TI, TD v PIDConL jsou pak řízené schedulerem; pro mimořádné situace lze GainSched přepnout do ručního
   režimu.

---

## Data z PCS 7 a historianu

- **CFC Trend Display** – export do CSV (výchozí oddělovače); pro identifikaci zaznamenávejte PV z budiče
  `Pcs7AnIn.PV_Out` a MV regulátoru.
- **Process Historian / WinCC** – export tagů do CSV / Excelu; aplikace zvládne společný čas, čas u každé
  veličiny i dlouhý formát (tag, čas, hodnota) a kódování UTF-16.
- Pro identifikaci si vyžádejte **nekomprimovaná** data (bez deadbandu archivace) s periodou aspoň 10× kratší než
  časová konstanta procesu.
