# Úkoly

## Sladit nové UI (React) s návrhem

Návrh: artefakt „PID Tools – nový návrh UI (všechny záložky)“, https://claude.ai/artifact/QuLnUL4JG1Y6jKfAGcmhD9
(záložky Data, Model, Ladění, Živá simulace, APC, Diagnostika, Přehled smyček, Projekt). Před začátkem načíst jeho
aktuální verzi – mohl se od 9. 10. 2026 změnit. Funkce a API zůstávají, mění se rozvržení a vzhled. Starý web
(Streamlit) už podle návrhu přestavěný je a dá se použít jako vodítko.

Zjištěno 28. 10. 2026 porovnáním snímků (návrh vs. `frontend/`):

- [x] **Hlavička** (10. 11.): smyčka, „+ Další smyčka“, souhrn dat, Projekt a report / Nastavení / „?“ (F1), záložky
      s podtržením.
- [x] **Pravý panel** (10. 11.): sbalovací karty, „Rozbalit vše / Sbalit vše“, hlavní tlačítko záložky.
- [x] **Data** (10. 11.): Zdroj dat jako přepínač, Signály smyčky s čipy DV, Statistika, Jednotky a rozsahy, Kvalita
      dat pod prohlížečem, Celý náhled s tabulkou (nové API `/dataquality`, `/datastats`, `/preview`).
- [x] **Model** (10. 11.): karty přenosů s FIT, „Identif.“, směrem účinku; Struktura modelu; štítky úseků s FIT.
- [x] **Ladění** (10. 11.): přepínač pohledů, společný graf PV + MV s kurzory Měření, Ukazatele kvality se
      zvýrazněním, karty Metoda / Návrh a sady / Scénář / Robustnost.
- [x] **APC** (10. 11.): doporučení se štítky, Průvodce v panelu, tabulka variant se zvýrazněním, Hodnoty do PCS 7.
- [x] **Diagnostika, Přehled smyček, Projekt** (10. 11.): karty podle návrhu.

Zbývá po sladění 10. 11. 2026:

- [x] **Živá simulace** (10. 11.): sdílený modul `live_ui.js` překreslen podle návrhu (lišta, graf PV / MV se
      značkami poruch a čárou „teď“, Ukazatele Sada 1 / Sada 2, karty s „?“); Streamlit má stejný vzhled.
      Zbývá: rychlosti 10× / 50× / 200× z návrhu, porucha „přes model DV“ (engine ji nemá).
- [ ] **APC:** štítky „nevhodné“ a „není potřeba“ – API vrací jen „doporučeno“ a „2. smyčka“.
- [ ] **Diagnostika:** graf provozních dat jako jedna karta s úseky A / B (návrh), karta „Co dál“; θ pro Harrise.
- [ ] **Data:** „Zoom / Měření“ nad prohlížečem, klik v grafu Celého náhledu skočí v tabulce; ruční čtení bez
      listu / hlavičky / oddělovače (API je nemá).
- [ ] **Projekt:** Automatické ukládání, „Nový“ projekt, jazyk reportu.
- [ ] **Model:** odhad po úsecích, stikce v kartě MV, počet vyřazených vzorků; „Identif.“ zapisuje `fx|` (Streamlit
      `idf|`).
- [ ] Ověřit tmavý vzhled a šířku ~1000 px u všech záložek.

## Další otevřené body

Podrobně v [milniky.md](milniky.md): M24 (vydávací workflow, instalátor zatím bez podpisu), M25 (kontrolní seznam
na čistém Windows bez sítě – ruční test), M27 (pilot), M28 (vypnutí staré aplikace, verze 4.0).
