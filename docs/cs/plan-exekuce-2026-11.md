# Exekuční plán oprav a vylepšení (listopad 2026)

Zadání: `docs/cs/audit-2026-11.md` (TICKET-001 … 020), `docs/cs/navrh-vylepseni-2026-11.md` (FEATURE-001 … 007).
Pravidla pro agenty: `AGENTS.md`.

## Společná pravidla vln

- **Základ:** integrační větev = stav beta 4 (`claude/vibrant-newton-uul6ny`, 32+ commitů před `main`). Každý úkol má
  větev `agent/<ID>` z integrační větve na začátku své vlny.
- **Slučování:** větve vlny se slučují po jedné. Tři soubory smí měnit víc úkolů ve vlně a konflikt řeší slučující:
  `pidtools/i18n/en.json` + `cs.json` (ponechat klíče obou stran), `pidtools/api/openapi.json` +
  `frontend/src/api/schema.d.ts` (vygenerovat znovu). Jiný konflikt = chyba plánu, zastavit.
- **Brána vlny (vždy):** `ruff check pidtools tests`; `cd frontend && npm run lint && npm run typecheck && npm test &&
  npm run build`; `python -m pytest -q` celé; zlaté případy beze změny; sonda prohlížeče
  bez chyb JS a bez přetékání (1 024 a 1 440 px).
- **Rozhodnutí vlastníka před vlnou 1:** TICKET-010 varianta A (odstranit Qt) nebo B. Bez rozhodnutí se TICKET-010
  vynechá; TICKET-016 pak maže jen texty nepoužité nikde.

## Stav (průběžně)

| Úkol | Stav | Commit |
|---|---|---|
| TICKET-005 šířka pravého panelu | hotovo, změřeno (340 px při 1 440, 300 px při 1 024) | ee0903c |
| TICKET-012 cesty jen `/api/v1`, zámky | hotovo | f00789c, 8878a82 |
| TICKET-020 e2e scénářů Ladění | hotovo, test prochází – chyba z beta 3 (bod 7) se nezopakovala | 8878a82 |
| TICKET-001 kontrola hodnot nastavení | hotovo; odchylka: odmítá se jen rozsah nulové šířky (meze se v rozhraní mění po jedné) | a2c5d82, 828100c |
| TICKET-003 hranice chyb, toasty | hotovo; chybí tlačítko „Uložit záchrannou kopii“ v kartě chyby (doplnit s TICKET-014) | d2d2c44 … 5f0c47b |
| TICKET-011 klient API | hotovo | 8c33b8f |
| TICKET-010 odstranění Qt (rozhodnutí vlastníka: varianta A) | hotovo; `asyncua` přesunuto do `requirements-dev.txt` | 39241c6 … ab86444 |
| FEATURE-001, TICKET-007, 008, 009 | hotovo (vlna 1 dokončena) | 329cec8 … 2c825f0 |
| TICKET-004 příznak `set2_defined` | hotovo | 8561395, 09ada67 |
| TICKET-006 cílené zneplatnění (17 → 9 požadavků) | hotovo | 8a6bcfb, b323c1b |
| TICKET-002 prostor bez vypršení, obnova | hotovo | ec7458e, 8185005 |
| TICKET-014 záchranná kopie při zavření, tlačítko v kartě chyby | hotovo v prohlížeči; desktop viz TICKET-021 | TICKET-014 commity |
| TICKET-015 číselná pole ukážou chybu u pole | hotovo | c1ac8d0 |
| TICKET-017 barvy z tokens.css; Trendy v tmavém vzhledu čitelné | hotovo | 9f4595a … 0ee67f5 |
| FEATURE-002 kopírování do schránky | hotovo | 6b2a419, 8a74016 |
| FEATURE-003 stav postupu na záložkách, „Next“; validace modelu se pamatuje | hotovo | 00d7545 … 80ea391 |
| TICKET-021 záchranná kopie při zavření okna desktopu | hotovo; sestavení a smoke test obalu v CI zelené | 0e2e3e2 |
| **Vlna 2 dokončena** | CI Tests + Desktop zelené nad 0e2e3e2 | |
| TICKET-013 typované nastavení (Ladění), neplatné výčty se vyřadí při načtení | hotovo | b40e492 … 96484b5 |
| TICKET-018 mypy v CI (api, workspace) | hotovo; Field(default=…) kvůli pydantic 2.14 | c7badbd … 3294696 |
| FEATURE-004 odečet, export a skrývání řad v grafech | hotovo | da49e9d, 75af140 |
| FEATURE-005 podzáložky Modelu, souhrnný pruh | hotovo | f957eaa … f5a5196 |
| TICKET-019 líné načítání záložek (822 → 410 kB) | hotovo | 42f6250 … 415ded9 |
| FEATURE-007 přehled smyček, hromadné identify / tune / accept / export | hotovo | dc8429c … 440e910 |
| **Vlna 3 dokončena** | lokálně 984 testů zelených; CI zelené nad e67108b | |
| FEATURE-006 zpět / znovu (nastavení, sady, úsek, scénář) | hotovo | d4138b8 … cad39cf |
| TICKET-016 úklid textů (3554 → 2993 klíčů), kontrola klíčů, test surových klíčů | hotovo | 50791fb … 03af7df |
| **Vlna 4 dokončena – celý plán hotový** | lokálně 1015 testů zelených | |

**TICKET-021 (nový, z kontroly TICKET-014, priorita HIGH pro desktop):** obal Tauri při zavření okna sidecar
natvrdo ukončí (`desktop/src/lib.rs`, `RunEvent::Exit` → `sc.kill()`), takže záchranná kopie odeslaná stránkou
(`pagehide` + `keepalive`) nemusí doběhnout. Návrh: nový endpoint `POST /api/v1/autosave/flush` (zapíše kopii všech
prostorů s neuloženými změnami, jen desktopový režim) a v Rustu před `kill()` jeho volání s časovým limitem ~2 s;
test: smoke test obalu (`--smoke`) ověří, že po změně a ukončení existuje kopie.

Úkoly běží po jednom (nebo po dvou nad různými soubory) přímo v integrační větvi; každý hotový úkol se hned pushuje.

Otevřené k rozhodnutí: `asyncua` (OPC UA) není v `requirements-api.txt`, takže vydávaný desktop i webový obraz se
staví bez něj a čtení z OPC UA v nich není dostupné (`/opc/available` vrací `false`). Přidat do
`requirements-api.txt`?

## Vlna 0 – mechanické změny napříč repozitářem (nic jiného neběží)

| Úkol | Soubory | Proč teď |
|---|---|---|
| TICKET-012 cesty jen `/api/v1`, zámky | `api/__init__.py`, `desktop/src/*.rs`, 25+ testů API | mění cesty ve většině testů – později by kolidoval se vším |
| TICKET-005 šířka pravého panelu | `styles/app.css`, `styles/compact.css` (smazat), `App.tsx` (1 řádek) | malá oprava, uvolní `App.tsx` |
| TICKET-020 e2e scénářů Ladění | nový `tests/test_frontend_tuning_scenarios.py` | jen nový soubor; základ pro regresi dalších vln |

**Před vlnou 1:** brána; `cargo test` a sestavení desktopu bez tagu (`release.yml`, instalovaný smoke test);
`.side` má 340 px při 1 440 px; výsledek TICKET-020 (prochází, nebo zapsaný postup chyby jako nový ticket).

## Vlna 1 – základy (8 souběžně)

| Úkol | Soubory |
|---|---|
| TICKET-001 kontrola hodnot nastavení | `api/data.py`, `app/project.py`, `tests/test_api.py` |
| TICKET-003 hranice chyb, toasty | nové `ErrorBoundary.tsx`, `Toasts.tsx`, `toasts.css`; `main.tsx`, `queryClient.ts`, `jobs.ts`, `data.ts` |
| TICKET-007 stavy a přepočet (bez příkladu v Ladění – ten udělá TICKET-013) | nové `QueryState.tsx`, `state.css`; `Card.tsx`, `StatusBar.tsx` |
| TICKET-008 přístupnost | `tuning.css`, `TuningMore.tsx`, `TriageTab.tsx`, `LoopsTab.tsx`, `JournalMain.tsx`, `QualityView.tsx`, `LineChart.tsx`, `BarChart.tsx`, nový `lib/a11y.ts` |
| TICKET-009 přesun modulů JS | `pidtools/ui/static` → `frontend/src/legacy`, `RecordViewer.tsx`, `Trend.tsx`, `LiveTab.tsx`, `legacy.d.ts`, `vite.config.ts`, `tools/build_sidecar.py`, 9 testů (cesty) |
| TICKET-010 Qt (podle rozhodnutí) | `pidtools/desktop/`, `tests/test_desktop.py`, `requirements-desktop.txt`, `tools/build_desktop.py`, `app/plots.py`, `tests.yml`, `README.md` |
| TICKET-011 klient API | `api/client.ts` |
| FEATURE-001 zkratky, uložení z hlavičky | nový `shortcuts.ts`; `App.tsx`, `ProjectTab.tsx`, `start/project.ts`, `Header.tsx`, `TuningTab.tsx`, `tuningState.ts`, `Guide.tsx` |

**Před vlnou 2:** brána; neplatné hodnoty nastavení vrací 422 a nic nevrací 500; chyba 422 ukáže toast a pole se vrátí;
F5 v Ladění počítá a stránku nenačte znovu, Ctrl+S uloží; 20× přepnutí Trendy ↔ Kvalita dat nechá jeden `.pidv`;
sestavení desktopu bez tagu (změna `build_sidecar.py`). **Doporučené vydání: beta 5** (opravy HIGH 001 a 003 + zkratky).

## Vlna 2 – navazující opravy a první funkce (8 souběžně)

| Úkol | Závisí na | Soubory |
|---|---|---|
| TICKET-002 prostor bez vypršení, obnova | 003, F-001 (`App.tsx`) | `api/sidecar.py`, `api/__main__.py`, `api/store.py`, `App.tsx`, nový `workspace.ts`, `queryClient.ts` |
| TICKET-004 příznak `set2_defined` | 001 | `app/tuning.py`, `app/workspace/tuning.py`, `app/workspace/__init__.py`, `api/tuning.py`, `app/live.py`, `app/report.py`, `tests/test_api_apc.py` |
| TICKET-006 cílené zneplatnění | 003 | nový `queryKeys.ts`; `data.ts`, `jobs.ts` |
| TICKET-014 uložení při zavření | F-001 (`start/project.ts`) | `start/project.ts`, `api/appsettings.py` |
| TICKET-015 chyby číselných polí | 001, 003 | `Fields.tsx`, `SetInput.tsx` |
| TICKET-017 paleta barev | 009 | nový `lib/palette.ts`; `RecordViewer.tsx`, `tokens.css` |
| FEATURE-002 schránka | 007 (`Card.tsx`), 003, F-001 (`TuningTab.tsx`) | nový `lib/clipboard.ts`; `TuningTab.tsx`, `Card.tsx`, místa s `Card` v Modelu a APC (jen přidání vlastnosti) |
| FEATURE-003 stav postupu, „Další krok“ | F-001 (`Header.tsx`) | `api/guide.py`, `app/guides.py`, `Header.tsx`, `ContextRow.tsx` |

**Před vlnou 3:** brána; projekt uložený v beta 4 se otevře se stejnými výsledky (migrace `set2_defined`); Set 2 zadaný
jako 1 / 100 / 0 se bere jako zadaný; po `DELETE` prostoru za běhu se nabídne obnova; změna `opt_ms` = nejvýš 9
požadavků; kopie Setu 1 má název bloku a jednotky. **Doporučené vydání: beta 6** (všechny opravy HIGH hotové).

## Vlna 3 – typy, struktura, větší funkce (6 souběžně)

| Úkol | Závisí na | Soubory |
|---|---|---|
| TICKET-013 typované nastavení (+ příklad `QueryState` v Ladění) | 001, 006, 007, F-002 | `api/data.py`, `data.ts`, `TuningTab.tsx`, `TuningMore.tsx`, `TuningProfile.tsx` |
| TICKET-018 mypy v CI | 004, 010 | nový `mypy.ini`; `requirements-dev.txt`, `tests.yml`, `app/workspace/__init__.py` |
| TICKET-019 líné načítání záložek | 002, 005, 009, F-001 | `App.tsx` |
| FEATURE-004 odečet a export v `LineChart` | 008, F-002 | `LineChart.tsx` |
| FEATURE-005 podzáložky Modelu | F-001, F-003 (`Header.tsx`, `Guide.tsx`) | `store.ts`, `Header.tsx`, `ModelTab.tsx`, `ModelSide.tsx`, `Guide.tsx`, `tests/test_frontend_model.py` |
| FEATURE-007 přehled projektu, hromadné akce | 004, F-001 (`ProjectTab.tsx`) | `api/audit.py` (nové endpointy sem, ne nový router), `ProjectTab.tsx`, `tabs/project/*` |

**Před vlnou 4:** brána + mypy; největší soubor sestavení pod 450 kB; žádná podzáložka Modelu přes dvě obrazovky;
hromadná identifikace 3 smyček (jedna bez MV) = 2× ok, 1× přeskočeno a Set 2 beze změny; odečet v grafu APC.

## Vlna 4 – po sobě (2 úkoly)

| Pořadí | Úkol | Závisí na | Soubory |
|---|---|---|---|
| 1 | FEATURE-006 zpět / znovu | 001, 013 (`api/data.py`), F-001, F-005 (`Header.tsx`) | `app/workspace/loops.py`, `api/data.py`, `api/tuning.py`, `Header.tsx`, `shortcuts.ts` |
| 2 | TICKET-016 úklid textů | vše předchozí (všechny úkoly přidávají klíče) | `pidtools/i18n/*.json`, nové `tools/i18n_check.py`, `tests/test_i18n_keys.py`; `i18n.tsx` |

**Před vydáním:** brána; tři změny a tři `Ctrl+Z` vrátí původní nastavení; kontrola textů hlásí 0 nepoužitých klíčů
a žádný surový klíč v rozhraní; plný průchod aplikací EN i CS; sestavení a smoke test instalátoru. **Vydání: 4.0.0-rc.1.**

## Přehled závislostí

```
Vlna 0: T012  T005  T020
Vlna 1: T001  T003  T007  T008  T009  T010  T011  F001
Vlna 2: T002  T004  T006  T014  T015  T017  F002  F003
Vlna 3: T013  T018  T019  F004  F005  F007
Vlna 4: F006 → T016
```
