# Změny

## Nevydáno

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
- Aplikační vrstva `pidtools/app` sdílená všemi frontendy (pracovní postup, formát projektu, protokol) – příprava
  desktopové verze pro inženýrské stanice; webová aplikace beze změny.
- Stránka APC rozdělená na moduly po strukturách.

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
