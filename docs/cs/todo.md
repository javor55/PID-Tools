# Úkoly

## Sladit nové UI (React) s návrhem

Návrh: artefakt „PID Tools – nový návrh UI (všechny záložky)“, https://claude.ai/artifact/QuLnUL4JG1Y6jKfAGcmhD9
(záložky Data, Model, Ladění, Živá simulace, APC, Diagnostika, Přehled smyček, Projekt). Před začátkem načíst jeho
aktuální verzi – mohl se od 9. 10. 2026 změnit. Funkce a API zůstávají, mění se rozvržení a vzhled. Starý web
(Streamlit) už podle návrhu přestavěný je a dá se použít jako vodítko.

Zjištěno 28. 10. 2026 porovnáním snímků (návrh vs. `frontend/`):

- [ ] **Hlavička:** výběr smyčky a „+ Další smyčka“ vlevo, popis souboru, vpravo tlačítka „Projekt a report“,
      „Nastavení“ (jazyk, vzhled …) a „?“; záložky jako druhý řádek s podtržením. Projekt není běžná záložka.
- [ ] **Pravý panel:** sbalovací karty s „Rozbalit vše / Sbalit vše“, nahoře velké hlavní tlačítko záložky
      (např. „Identifikovat model“).
- [ ] **Data:** karty Kvalita dat (seznam kontrol s ikonami a vysvětlením), Statistika (min / max / průměr / σ),
      Jednotky a rozsahy; zdroj dat jako přepínač Soubor / Ukázka / OPC UA. Prohlížeč záznamu zůstává (pozdější
      rozhodnutí), návrh „Záznam smyčky“ nahrazuje.
- [ ] **Model:** karta na každý přenos (Přenos 1 · MV, Přenos 2 · DV) s typem, parametry, zaškrtnutím „Identif.“,
      směrem účinku, původními hodnotami a FIT; karta Struktura modelu; štítky úseků s FIT a šrafované vyřazené
      části u grafů; tabulky modelů a porovnání struktur podle návrhu.
- [ ] **Ladění:** přepínač pohledů Scénář v čase / Frekvenční analýza / Všechny metody, časová osa a Měření;
      společný graf PV + MV s kurzory; Ukazatele kvality se zvýrazněnou lepší hodnotou; v panelu karty Metoda
      ladění, Návrh a sady v PLC (sloupce Návrh / Sada 1 / Sada 2, tlačítka „Návrh → Sada 2 / 1“), Scénář simulace
      a dlaždice Robustnost. Blok PIDConL přesunout podle návrhu.
- [ ] **Živá simulace:** porovnat s návrhem (Live.dc.html) – panel nástrojů, ukazatele, karty vpravo.
- [ ] **APC:** štítky doporučení (doporučeno / nevhodné / není potřeba / 2. smyčka); v panelu Průvodce, Model
      poruchy, Nastavení techniky; výsledek jako tabulka variant (např. Bez FF / Statická / Dynamická) se zvýrazněním;
      Hodnoty do PCS 7 jako samostatná karta. Projít všech 11 technik.
- [ ] **Diagnostika, Přehled smyček, Projekt:** porovnat s Diag.dc.html, Audit.dc.html, Project.dc.html.
- [ ] **Postup:** po záložkách, ke každé snímek návrh vs. nové UI do PR; testy v prohlížeči (`tests/test_frontend.py`)
      musí dál procházet. Při kontrole hlídat vzhled podle návrhu, ne jen funkce.

## Další otevřené body

Podrobně v [milniky.md](milniky.md): M24 (vydávací workflow, instalátor zatím bez podpisu), M25 (kontrolní seznam
na čistém Windows bez sítě – ruční test), M27 (pilot), M28 (vypnutí staré aplikace, verze 4.0).
