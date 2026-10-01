# PID Tools

**Identifikace procesu z provozních dat a ladění regulátoru PIDConL (SIMATIC PCS 7 APL) – včetně pokročilých
regulačních struktur (APC).**

Webová aplikace pro procesní a automatizační inženýry. Z exportu historianu nebo PCS 7 identifikuje model procesu,
navrhne parametry regulátoru, ukáže jejich robustnost a očekávané chování a vytvoří protokol z ladění s tím, co
přesně nastavit v PCS 7. Metody platí obecně pro průmyslové PID regulátory; terminologie, struktura regulátoru
a implementační kroky odpovídají bloku **PIDConL** a šablonám knihovny **APL**.

- **Online:** <https://pidtools.streamlit.app/> (veřejná instance – viz [Data a bezpečnost](#data-a-bezpečnost))
- **Dokumentace:** [Uživatelská příručka](docs/prirucka.md) · [Metody](docs/metody.md) ·
  [Implementace v PCS 7](docs/pcs7.md) · [Nasazení a provoz](docs/nasazeni.md) · [Změny](CHANGELOG.md)

> *English:* PID Tools identifies process models from plant data and tunes the PIDConL controller of SIMATIC PCS 7
> APL, incl. cascade, feedforward, decoupling, override, Smith predictor and gain scheduling. The UI is available in
> Czech and English (Settings › Language). The documentation in `docs/` is in Czech.

---

## K čemu je

| Úloha | Co aplikace udělá |
|---|---|
| **Přeladění smyčky** | z nahraného skokového testu nebo provozních dat identifikuje model, navrhne PI/PID a porovná ho se současným nastavením (robustnost i simulace) |
| **Smyčka kmitá / je líná** | diagnostika provozu: výkon smyčky, oscilace, stikce ventilu, nelinearita; ukáže, zda pomůže přeladění, nebo je problém jinde |
| **Návrh APC** | kaskáda, dopředná vazba, rozvazbení 2×2, override, Smithův prediktor, gain scheduling – s průvodcem *kdy použít* a hodnotami pro šablony APL |
| **Dokumentace změny** | protokol z ladění (HTML → PDF): původní a nové parametry, robustnost, očekávaná odezva, modely, podpisy |

## Hlavní funkce

- **Data** – CSV / Excel z historianu nebo PCS 7: společný časový sloupec, vlastní čas u každé veličiny i „dlouhý“
  formát (tag, čas, hodnota); čas jako číslo nebo datum v českém, ISO, US či evropském formátu; kódování UTF-8,
  UTF-16 i windows-1250. Sloupce PV / MV / SP se předvyplní podle názvů tagů. Kontrola kvality dat (komprese
  historianu, počet a velikost skoků, šum) a automatické hledání úseků vhodných pro identifikaci.
- **Identifikace** – modely 0., 1. a 2. řádu a integrační, vždy s dopravním zpožděním a s modely měřených poruch;
  potlačení neměřených poruch, vynucení znaménka zesílení, odhad stikce ventilu, zafixování známých parametrů,
  nejistota modelu (bootstrap), ověření na jiném úseku a detailní hodnocení (FIT, rezidua).
- **Ladění PIDConL** – SIMC, iSIMC, Lambda, AMIGO, průměrovací ladění hladiny a numerická optimalizace (MIGO,
  IAE, ISE, ITAE, limit překmitu, celý scénář) vždy s podmínkou robustnosti Ms. Konfigurace bloku jako v PCS 7
  (NormPV/NormMV, SampleTime, DiffGain, P/D ze zpětné vazby, deadband, limity a rychlost MV, filtr PV, rampa SP).
  Dvě sady parametrů (současná / nová), porovnání všech metod, simulace scénářů s ventilem, stikcí a šumem.
- **Živá simulace** v prohlížeči – plynulá, okamžitá reakce na SP, ruční MV, poruchy a šum, zrychlení až 500×.
- **APC** – kaskáda, dopředná vazba (statická i lead-lag), rozvazbení 2×2 (RGA, decouplery), override (výběr
  MIN/MAX s externí zpětnou vazbou), Smithův prediktor, gain scheduling podle PV nebo regulační odchylky; každá
  struktura s průvodcem, simulací přínosu a hodnotami pro šablony APL.
- **Více smyček v jednom projektu** (např. vnitřní a vnější smyčka kaskády z jednoho exportu).
- **Projekt** (JSON) s modely, laděním a volitelně daty; **automatické ukládání** rozpracované práce v prohlížeči.
- **Protokol z ladění** (HTML, tisk do PDF) pro všechny smyčky projektu.
- **Průvodce v každé záložce** – k čemu záložka je, postup, kterou metodu kdy zvolit, tipy z praxe a kontrolní
  seznam podle stavu projektu. Rozhraní česky i anglicky.

## Rychlý start

### Online
Otevřete <https://pidtools.streamlit.app/>, zvolte **Demo** a projděte záložky 1–6 – každá má vlastního průvodce (📖).

### Lokálně (Windows)
1. Nainstalujte [Python 3.11](https://www.python.org/downloads/) (při instalaci zaškrtněte *Add Python to PATH*).
2. Stáhněte repozitář (*Code › Download ZIP*) a rozbalte.
3. Spusťte **`start.bat`** – nainstaluje knihovny a otevře aplikaci v prohlížeči (<http://localhost:8501>).

### Lokálně (Linux / macOS)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Podrobnosti, provoz na interním serveru a aktualizace: [docs/nasazeni.md](docs/nasazeni.md).

## Postup v kostce

1. **Data** – nahrajte export, zkontrolujte sloupce PV / MV / SP (případně měřené poruchy) a vyberte úsek
   s výraznými změnami MV (skokový test v ručním režimu) nebo SP (v automatu).
2. **Model** – spusťte identifikaci, vyberte model s dobrou shodou, zkontrolujte rezidua a ověřte ho na jiném úseku.
3. **Ladění** – nastavte blok PIDConL jako v PCS 7 (hlavně **rozsah NormPV / NormMV**), do Set 1 zadejte současné
   parametry z faceplatu, zvolte metodu a nový návrh převezměte do Set 2. Porovnejte Ms a simulaci.
4. **Živá simulace** – vyzkoušejte obě sady interaktivně.
5. **APC** – podívejte se na doporučení; pokročilé struktury jsou volitelné.
6. **Projekt a report** – uložte projekt a vytvořte protokol z ladění.

Podrobně: [Uživatelská příručka](docs/prirucka.md).

## Metody v kostce

**Modely** (vše s dopravním zpožděním θ): 0. řád (K), 1. řád (K, T1 – FOPDT), 2. řád (K, T1, T2 – SOPDT),
integrační (Ki) a integrační s 1. řádem (Ki, T1). Volí se podle shody s daty a toho, zda se proces ustálí.

| Metoda ladění | Kdy ji použít |
|---|---|
| **SIMC** | univerzální výchozí volba; jeden parametr τc (výchozí = θ, větší = pomalejší a robustnější) |
| **iSIMC** | samoregulační proces s výraznějším zpožděním, kde SIMC vychází zbytečně opatrně |
| **Lambda (IMC)** | klidná odezva bez překmitu, navazující smyčky; poruchy dorovnává pomaleji |
| **AMIGO** | bezpečné první nastavení bez ladicího parametru (Ms ≈ 1,4); nejistý nebo proměnný proces |
| **Průměrovací** | vyrovnávací nádrže – klidný odtok, hladina smí kolísat v mezích |
| **Optimalizace** | ověřený model a snaha vytěžit maximum; MIGO (nejrychlejší potlačení poruch při dané robustnosti), IAE / ISE / ITAE, limit překmitu nebo přímo váš scénář |

**Robustnost:** Ms (maximum citlivosti) 1,4 velmi robustní, 1,6 obvyklé, 2,0 hraniční; dále amplitudová (GM)
a fázová (PM) bezpečnost a šum MV.

| Struktura APC | Kdy ji použít |
|---|---|
| **Kaskáda** | porucha jde přes rychlejší měřitelnou veličinu (průtok, tlak); stikce nebo nelinearita ventilu |
| **Dopředná vazba** | měřená porucha s výrazným vlivem na PV; regulátor se ladí normálně, dopředná vazba až potom |
| **Rozvazbení 2×2** | dvě smyčky se navzájem ovlivňují (RGA daleko od 1) |
| **Override** | jeden ventil, hlavní úkol + mez jiné veličiny (tlak, teplota, výkon) |
| **Smithův prediktor** | dopravní zpoždění převládá (θ/(θ+T) ≳ 0,5) a je stálé |
| **Gain scheduling** | nelineární proces v širokém rozsahu (podle PV) nebo rychlejší návrat z velkých odchylek (podle ER) |

Vysvětlení všech metod, kritérií a ukazatelů: [docs/metody.md](docs/metody.md).

## Data a bezpečnost

- Nahraná data se zpracují na serveru, kde aplikace běží, **jen po dobu relace** a nikam se neukládají (žádné
  zápisy na disk, žádná volání externích služeb, telemetrie Streamlitu je vypnutá).
- Rozpracovaná práce se automaticky ukládá **jen v prohlížeči uživatele** (lze vypnout v záložce Projekt a report).
- Veřejná instance běží na Streamlit Community Cloud. Pokud provozní data nesmíte nahrávat na cizí server,
  spusťte aplikaci **lokálně nebo na interním serveru** ([docs/nasazeni.md](docs/nasazeni.md)).

## Upozornění

Výsledky jsou **návrhem odvozeným z modelu**, který je vždy jen přiblížením procesu. Před nasazením parametry
posuďte, změny zavádějte postupně a ověřte je na zařízení podle pravidel vašeho provozu. Odpovědnost za nasazení
nese uživatel. Názvy parametrů bloků APL se mohou mezi verzemi knihovny lišit – ověřte je v dokumentaci své verze.

## Pro vývojáře

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest                                          # vše (~9 min, celá aplikace přes Streamlit AppTest)
python -m pytest tests/test_core.py tests/test_basic.py   # jen výpočetní jádro (rychlé)
```

```
app.py                     vstupní bod – skládá stránku z modulů níže
pidtools/
  core/                    výpočty bez závislosti na Streamlitu
    models.py              struktury modelů, simulace odezvy, predikce
    identification.py      fit modelů, stikce, neměřené poruchy, hodnocení, nejistota, přepočet rozsahů
    tuning.py              pravidla ladění a optimalizace
    robustness.py          kmitočtová analýza (stabilita, Ms, GM, PM), šum MV
    simulation.py          PIDConL / ventil / proces krok po kroku (dávková, kaskáda, živá)
    apc.py                 rozvazbení (RGA), override, Smithův prediktor, návrh dopředné vazby
    gainsched.py           gain scheduling (blok GainSched), řídicí pásmo
    diagnostics.py         výkon smyčky, oscilace, stikce, kvalita dat, úseky, nelinearita
    demo.py, util.py
  i18n/                    texty: cs.py, en.py, T()
  ui/                      rozhraní ve Streamlitu
    context.py             Ctx – data sdílená záložkami v jednom běhu
    widgets.py charts.py theme.py dataio.py cache.py project.py
    loops.py               více smyček v projektu (snímky stavu, přepínání)
    ff.py                  dopředná vazba – stav sdílený Laděním a APC
    guess.py               odhad rolí PV/MV/SP podle názvů tagů
    report.py              protokol z ladění (HTML)
    autosave.py            automatické ukládání v prohlížeči
    static/                živá simulace v prohlížeči (live_engine.js = port core/simulation.py)
    pages/                 jeden modul na záložku: header, data, model, tuning, live, diagnostics,
                           apc (+ apc_guide, cascade), project, guides
tests/                     pytest: jádro, celá aplikace (AppTest), načítání dat, smyčky, APC
docs/                      uživatelská dokumentace
```

Uvnitř jádra jsou všechny procesní veličiny v % rozsahů regulátoru (NormPV, NormMV), takže zesílení procesu
i Gain regulátoru jsou bezrozměrné jako v PIDConL. Data a výsledky se uživateli ukazují v reálných jednotkách.
