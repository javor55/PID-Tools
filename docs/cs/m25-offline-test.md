# M25 – ruční ověření na čistém Windows bez sítě

Kontrolní seznam pro instalátor z GitHub Release (workflow `release.yml`). Provádí se jednou na **Windows 10** a jednou
na **Windows 11**, ideálně na čistém počítači nebo virtuálním stroji, který nikdy neměl PID Tools ani vývojové nástroje.
Výsledky zapište do tabulky na konci a přiložte k pilotu (M27).

## Příprava

1. Stáhněte z vydání `PID-Tools-<verze>-setup-offline.exe` (obsahuje WebView2), `SHA256SUMS.txt` a z repozitáře
   `tools/check_offline.ps1` a ukázkový projekt (např. `tests/golden/tic001.json` přejmenovaný na `.pidproj`).
2. Ověřte kontrolní součet: `Get-FileHash .\PID-Tools-<verze>-setup-offline.exe` = hodnota v `SHA256SUMS.txt`.
3. **Odpojte síť** (vypněte síťový adaptér / Wi-Fi, u VM odpojte virtuální síť).
4. Spusťte `powershell -ExecutionPolicy Bypass -File check_offline.ps1` a nechte ho běžet celou dobu testu.

## Kontrolní seznam

| # | Krok | Očekávání |
|---|---|---|
| 1 | Spusťte instalátor | SmartScreen hlásí neznámého vydavatele (instalátor není podepsaný) → *Další informace › Přesto spustit*. Instalace bez práv správce, bez chyby, i bez sítě (WebView2 je přibalený). |
| 2 | Start z nabídky Start | Okno „PID Tools“ do ~10 s, stav vlevo dole „Připojeno k výpočtům“. Žádné okno konzole. |
| 3 | Start – ukázková data | Tlačítko „Vyzkoušet na ukázkových datech“ načte demo; v hlavičce „1 soubor · 1 smyčka“. |
| 4 | Data › Zdroje a smyčky | Přidání vlastního CSV (přetažením i tlačítkem), tabulka smyček, „Navrhnout podle názvů tagů“. |
| 5 | Data › Trendy, Kvalita dat, Diagnostika | Grafy se vykreslí, kurzory A–B ukazují hodnoty, „Přepočítat verdikty“ doběhne. |
| 6 | Model | „Identifikovat model“ doběhne (průběh úlohy), karta Ověření modelu ukáže tabulku a graf. |
| 7 | Ladění | Návrh SIMC, tabulka robustnosti, „Export pro řídicí systém“ uloží soubor (dialog Uložit jako). |
| 8 | APC | Doporučení se štítky, karta dopředné vazby, Hodnoty do PCS 7. |
| 9 | Živá simulace | Start, rychlost 50×, porucha DV, „Zapsat výsledek do deníku“. |
| 10 | Nastavení | Změna jazyka (CZ ↔ EN), Nastavení › Regulátory: knihovna, „Vytvořit vlastní“, test použitelnosti. |
| 11 | Projekt › Uložit | Uložení `.pidproj` do Dokumentů; Projekt › Deník: „Uložit verzi“, změna stavu. |
| 12 | Report | „Vytvořit report“ a stažení; soubor se otevře v prohlížeči i bez sítě a obsahuje grafy. |
| 13 | Zavřít a otevřít poklepem | Poklep na uložený `.pidproj` v Průzkumníku spustí aplikaci a projekt otevře; druhý poklep při běžící aplikaci ho otevře ve stejném okně. |
| 14 | Obnova po pádu | Za běhu ukončete `pidtools-desktop.exe` ve Správci úloh, spusťte znovu → nabídka obnovy záchranné kopie. |
| 15 | Síť | `check_offline.ps1` po Ctrl+C: „žádné spojení mimo 127.0.0.1“. |
| 16 | Procesy po zavření | Po zavření okna nezůstane ve Správci úloh `pidtools-api.exe`. |
| 17 | Odinstalace | Nastavení › Aplikace › PID Tools › Odinstalovat; složka instalace zmizí, poklep na `.pidproj` už PID Tools nespouští. Uložené projekty v Dokumentech zůstanou. |

Varianta s internetem (jen jednou, Windows 11): `PID-Tools-<verze>-setup.exe` (bez přibaleného WebView2) a `.msi`
s tichou instalací `msiexec /i PID-Tools-<verze>-x64.msi /qn` – kroky 1–3 a 17.

## Výsledky

| Systém (verze, build) | Instalátor | Kroky OK | Problémy (číslo kroku, popis, snímek) | Kdo / kdy |
|---|---|---|---|---|
| Windows 10 22H2 | setup-offline | | | |
| Windows 11 24H2 | setup-offline | | | |
| Windows 11 24H2 | setup + msi (online) | | | |
