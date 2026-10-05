# Změny

## Nevydáno

- Data: načte se export trendu z WinCC (UTF-16, `;`, dvojice `X Time` / `X ValueY`); prázdné sloupce (nepoužité
  křivky) se vynechají a veličiny se jmenují podle křivky (`PV_Out`, ne `PV_Out ValueY`). Dlouhé záznamy se načítají
  rychleji (formát času se rozpozná na vzorku, rychlý parser CSV při jednoznačném oddělovači).
- Web: u dlouhých záznamů (např. 24 h po 1 s) už každé kliknutí netrvá 15+ s – automaticky nalezené úseky se
  do grafu vloží najednou (vyznačí se nejvýš 40); grafy zřeďují i průběhy s mezerami.
- Rozsah regulátoru (NormPV / NormMV) zadaný v bloku PIDConL zůstane, i jako 0–100 při datech mimo něj (např. pro
  srovnání s blokem v PLC); dřív ho odhad z dat přepsal. Data těsně mimo 0–100 (MV −0,004 %) už odhad nezmění
  na −10–100.
- Automaticky nalezené úseky: bez modelu úsek pokračuje, dokud PV na skok zřetelně nezareaguje (2,5× doba do odezvy);
  při velkém zpoždění dřív skončil dřív, než se PV pohnulo. Varování „T1 delší než úsek“ upozorní i na úsek tvořený
  hlavně poruchami a regulací v AUTO.
- Kvalita dat: MV saturovaná na limitu v datech z historianu (0,00 … 0,2 %, ne přesně 0) se počítá jako MV na
  limitu, takže úsek s dlouhou saturací dostane varování.

## 3.2.1 beta – rychlejší start desktopu, kontrola Set 1 u identifikace v uzavřené smyčce

**Beta:** k testování; problémy prosím hlaste.

- Identifikace se smyčkou v AUTO (web i desktop): upozornění, když Set 1 neodpovídá regulátoru v záznamu (simulace
  smyčky s modelem a Set 1 sedí na PV pod 50 % nebo je nestabilní), a tlačítko **Odhadnout Set 1 ze záznamu**
  (PI regulátor z pohybů MV proti odchylce, metoda nejmenších čtverců).
- Desktop startuje rychleji: SciPy a Plotly se načtou až při prvním použití a hned se ukáže úvodní obrazovka
  s ikonou.
- Grafy v desktopu: odečet kurzoru už nemění velikost grafů (např. ve frekvenční analýze).

## 3.2.0 beta 1 – aplikace pro Windows (instalátor), připomínky k ovládání, načítání dat

**Beta:** první sestavení instalátoru pro Windows a samostatného webového offline balíčku – problémy prosím hlaste.

- Data: soubor, u kterého se nepodaří rozpoznat čas (nebo se čas nemění), se otevře po řádcích – co řádek, to
  vzorek; periodu řádku nastavíte v Rozložení souboru a čas (s, ms, min, h). Rozpozná se čas s názvem měsíce
  (Aug-04-07 20:47:20), CSV s celými řádky v uvozovkách (IP.21 přes Excel) a přeskočí se prázdné řádky.
- Desktop startuje zhruba dvakrát rychleji (panely APC vznikají až při otevření, offline balíček obsahuje bytecode).
- Grafy v desktopu: tlačítka s textem (Celý rozsah, Kurzor, Měření, PNG, CSV, Kopírovat, Okno); Celý rozsah
  zobrazí celý záznam najednou; zoom a posun jen v čase, osa y se přizpůsobí viditelným datům; dvojklik = celý rozsah.
- Model (desktop i web): jedna sada grafů – záznam s úsekem, model, rezidua a měřené poruchy; parametry pod sebou.
- Ladění: blok PIDConL je sekce 1 a NormPV / NormMV se odhadnou z dat, dokud jsou na výchozích 0–100; scénář se
  současnými sadami je vidět hned; výchozí návrh je optimalizace, PI, IAE s omezením překmitu, skok SP i porucha.
- Sekce panelu nastavení jsou na začátku sbalené; parametry dopředné vazby pod sebou.
- Data: statistika veličin smyčky (min, max, průměr, σ) v pravém panelu (desktop i web).
- Desktop: kolečko myši už nemění číselná pole ani výběry (posune se panel).
- Přehled smyček: seznam smyček a pod ním nastavení vybrané smyčky pod sebou (místo široké tabulky) na webu
  i v desktopu; smyčky se najdou i s příponou za rolí („.PV IP_ANALOGMAP“) a bez tagů se navrhne jedna smyčka
  z rolí sloupců (CV / MV / SP); názvy smyček zůstávají v původním zápisu tagu.
- Desktop: přepnutí na APC už okno nezamrazí – simulace velmi pomalých procesů mají omezený počet kroků
  (dopředná vazba, gain scheduling, kaskáda, split range, VPC, poměr i protokol).
- Živá simulace (desktop i web): v AUTO je pole MV zašedlé a ukazuje živou hodnotu MV, v MAN je zašedlá SP;
  přepnutí do MAN ponechá současné MV (bez rázu).
- Windows: desktopová aplikace je klasická aplikace pro Windows s vlastní ikonou – instalátor
  `PID-Tools-<verze>-setup.exe` (pro uživatele, bez práv správce, nabídka Start, odinstalace v Nastavení) a přenosný
  ZIP s `PID Tools.exe`; webová aplikace má vlastní offline balíček (`PID-Tools-<verze>-web-win64-offline.zip`,
  se zdrojem OPC UA). Ikona aplikace v okně desktopu i na kartě prohlížeče.
- Ladění: vysvětlení, kam působí události SP, vstup procesu a PV (výstup) – u scénáře i v editoru událostí.
- Živá simulace se pozastaví, když se přepne na jinou záložku (nebo kartu prohlížeče) či okno minimalizuje.
- Více smyček (web i desktop): nová smyčka dostane vlastní název (Smyčka n) a otevře se na záložce Data pro výběr
  signálů; smyčku lze přímo přejmenovat (web: menu ⋮ vedle přepínače smyček, desktop: Přejmenovat smyčku).
- Ladění v desktopu: přepsání sady 1 / 2 hned přepočítá graf scénáře; TI a TD nemohou být záporné.
- Diagnostika v desktopu: graf nelinearity (lokální zesílení podle MV), hodnocení a odkaz na gain scheduling jako na webu.

## 3.1.0 – frekvenční analýza, přehled smyček, OPC UA, rozšíření APC

**Vývoj**
- Offline balíček pro Windows obsahuje desktopovou aplikaci (`PID-Tools-desktop.bat`, PySide6-Essentials).
- Oprava: volby znaménka zesílení v záložce Model ukazovaly text tlačítka gain schedulingu.
- Desktopová aplikace (náhled, `python -m pidtools.desktop`, PySide6 + pyqtgraph): Data, Model, Ladění se
  scénářem a srovnáním metod, validace a nejistota modelu, živá simulace, APC (kaskáda, dopředná vazba,
  rozvazbení, override, Smithův prediktor, gain scheduling podle PV a ER), diagnostika provozu, více smyček,
  projekty zaměnitelné s webovou aplikací, export protokolu, okno nápovědy s průvodci záložek (obsah sdílený
  s webem), automatické ukládání s nabídkou obnovení při dalším spuštění, proklik z doporučení APC.
- Kontrolní seznamy struktur APC počítané ve sdílené vrstvě – na webu i v desktopu stejné.
- Rozložení desktopu: každá záložka má vlevo co největší plochu pro grafy a data a vpravo panel nastavení se
  sbalitelnými sekcemi (stav i šířka panelu se pamatují); kompaktní číselná pole.
- Ladění v desktopu: nejdřív scénář (výchozí skok SP; porucha na vstupu či výstupu, skok měřené poruchy, přehrání
  naměřených poruch, vlastní události), potom návrh; nic se nepočítá před stiskem **Vypočítat (F5)**, změny označí
  výsledek jako neaktuální; návrh se ukáže jako třetí křivka ještě před zápisem do sady; optimalizace ve výchozím
  stavu cílí na scénář; historie ladění s návratem do sady (ukládá se do projektu).
- Grafy v desktopu: kurzor s hodnotami všech křivek, dva měřicí kurzory (Δt, ΔY), celý rozsah, export PNG / CSV,
  kopie do schránky, samostatné okno (druhý monitor), skrytí křivky kliknutím na legendu.
- Desktop: nedávné soubory, přetažení dat a projektů do okna, zkratky Ctrl+1…7 pro záložky, zapamatovaná velikost
  okna, přehled klávesových zkratek v Nápovědě.
- Frekvenční analýza (Bode, Nyquist s kružnicí Ms, |S| a |T|, šířka pásma) sady 1, sady 2 a návrhu – web i desktop.
- Identifikace v uzavřené smyčce z dat se smyčkou v AUTO (změny SP): nepřímá metoda se simulací celé smyčky
  s regulátorem ze záznamu; pro srovnání se ukáže model z otevřené smyčky.
- Přehled smyček (záložka 7): více smyček z jednoho souboru, pořadí podle problémů, společné oscilace a jejich
  zdroj, otevření smyčky jako smyčky projektu.
- APC: split range, regulace polohy ventilu, poměrová regulace s křížovým omezením, interakce N×N (RGA,
  Niederlinskiho index, doporučené párování).
- OPC UA (jen čtení): procházení, historie a záznam živých hodnot v desktopu; zdroj dat OPC UA v lokálním webu.
- Webové rozhraní v rozložení desktopu: grafy vlevo, nastavení ve sbalitelných sekcích vpravo na všech záložkách;
  ladění s předvolbami scénáře a tlačítkem Vypočítat; Model, Data s diagnostikou, APC, živá simulace a projekt.
- Aplikační vrstva `pidtools/app` sdílená všemi frontendy (pracovní postup, formát projektu, protokol) – příprava
  desktopové verze pro inženýrské stanice; webová aplikace beze změny.
- Stránka APC rozdělená na moduly po strukturách.
- Připravenost k nasazení: CI s lintem a testy při každém pushi, uživatelské názvy escapované ve výstupu HTML,
  žádná varování Session State na webu, ukázka předvybírá měřenou poruchu.

## 3.0.0 – první verze pro sdílení v týmu

**Data**
- Náhled načtených dat, vlastní časový sloupec u každé veličiny, dlouhý formát (tag, čas, hodnota), časy v českém,
  ISO, US a evropském formátu, odhad rolí PV / MV / SP podle názvů tagů.
- Kódování CSV: UTF-8, UTF-16 (WinCC, Excel „Unicode text“) i windows-1250; podpora starších souborů `.xls`.
- Bezpečné přepínání mezi ukázkou, souborem a projektem (nastavení se nenulují, model patří ke svým datům,
  nahraný soubor se pamatuje).
- Rozsah regulátoru NormPV / NormMV přesunutý do bloku PIDConL v Ladění; upozornění, když data leží mimo rozsah
  nebo zůstal výchozí 0–100; změna rozsahu model jen přepočítá.

**Ladění a simulace**
- Živá simulace přímo v prohlížeči: plynulá, porovnání sad, poruchy různých tvarů, šum a filtr, změna procesu,
  ukazatele, události, export CSV / PNG.
- Porovnání „Sada 2 bez dopředné vazby“ ve scénáři; řídicí pásmo ConZone v simulaci PIDConL.

**APC**
- Kaskáda, dopředná vazba (přesunutá z Ladění; zesílení v jednotkách MV pro FFwd, simulace bez / statická /
  dynamická), rozvazbení 2×2 (RGA, decouplery), override s external reset, Smithův prediktor (hodnoty pro šablonu
  SmithPredictorControl), gain scheduling podle PV i podle regulační odchylky.
- Doporučení struktur podle modelů a vazeb mezi smyčkami, průvodce s implementací pomocí šablon APL.

**Projekt a protokol**
- Více smyček v jednom projektu, projekt jedním kliknutím, automatické ukládání v prohlížeči.
- Protokol z ladění (HTML → PDF) pro všechny smyčky: co nastavit v PCS 7, robustnost, očekávaná odezva, APC, podpisy.

**Rozhraní a dokumentace**
- Nativní světlý / tmavý vzhled, průvodci ve všech záložkách (výchozí sbalení), aktualizovaná nápověda s glosářem
  a částí *O aplikaci* (verze, upozornění, data).
- Dokumentace v `docs/` (anglicky; česká verze v `docs/cs`): příručka, metody, implementace v PCS 7, nasazení; nové README.
- Provoz: vypnutá telemetrie Streamlitu, skryté vývojářské volby, `Dockerfile` pro interní server, opravený
  devcontainer, ohraničené verze knihoven.

## 2.0.0
- Identifikace modelů s dopravním zpožděním a měřenými poruchami, ladění PIDConL (SIMC, iSIMC, Lambda, AMIGO,
  průměrovací, optimalizace), robustnost, simulace scénářů, diagnostika, projekt a report, čeština a angličtina.
