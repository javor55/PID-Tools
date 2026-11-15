# AGENTS.md – pravidla pro vývojové agenty (PID Tools)

Zadání: `docs/cs/audit-2026-11.md` (TICKET), `docs/cs/navrh-vylepseni-2026-11.md` (FEATURE), pořadí: `docs/cs/plan-exekuce-2026-11.md`.

## Architektura
1. Vrstvy `pidtools/core` (numerika bez I/O) → `pidtools/app` (Workspace, bez FastAPI a UI) → `pidtools/api` (tenké routery) → `frontend/src`. Import jen směrem dolů (hlídá `tests/test_app_layer.py`).
2. API jen pod `/api/v1`. Tělo i odpověď endpointu = model Pydantic, ne `dict`. Špatný vstup = 4xx s textem, nikdy 500.
3. `pidtools/api/openapi.json` a `frontend/src/api/schema.d.ts` jsou generované: po změně API `python -m pidtools.api --openapi pidtools/api/openapi.json && (cd frontend && npm run api-types)`. Ručně je neupravuj a při konfliktu je vygeneruj znovu.
4. Nový klíč nastavení smyčky = `STATE_KEYS` + typ a meze v `app/project.py` + výchozí hodnota ve `workspace/__init__.py: DEFAULTS`. Hodnoty se kontrolují před zápisem.
5. Výpočet delší než 1 s běží jako úloha (`app/jobs.py`), ne uvnitř požadavku.
6. Zlaté případy (`tools/golden.py`) se nesmí změnit bez výslovného zadání. Logika regulátoru a živé simulace je v Pythonu i v JS (`ctrl_engine.js`, `live_engine.js`): měň obojí, hlídají testy shody.
7. Formát projektu `.pidproj` je zpětně kompatibilní: nový klíč = migrace při načtení + test se starým souborem.

## Frontend
8. Data serveru jen přes TanStack Query (`useWsQuery`, `useWsMutation`, `usePatchSettings`); Zustand jen pro stav rozhraní. `fetch` jen v `api/client.ts`.
9. Typy z `api/schema.d.ts`. Zakázáno: `any`, `as unknown as`, `Record<string, unknown>` pro data API, vlastní výchozí hodnoty nastavení (`st.x ?? 100`).
10. Každé asynchronní volání má ošetřenou chybu (hlášení uživateli); `void promise()` bez zachycení je zakázáno. Optimistická změna se při chybě vrací.
11. Každý pohled má stav načítání, prázdno a chyba a ukazuje probíhající přepočet (`aria-busy`); ne znak „…“ a ne stará čísla bez označení.
12. Texty jen přes `T("klíč")`, klíč do `pidtools/i18n/en.json` i `cs.json` (odsazení jednou mezerou, nové klíče na konec). Žádný pevný text v TSX, žádné `dangerouslySetInnerHTML`.
13. Barvy a velikosti jen z `styles/tokens.css`; žádné `#rrggbb` v TSX. Nepřebíjej styly dalším souborem (pořadí importů CSS není zaručené) – uprav pravidlo u zdroje.
14. Klikací prvek je `button` (nebo `tabIndex` + Enter / mezerník), pole má přístupný název, text kontrast ≥ 4,5 : 1, prvky pro testy mají `data-testid`.
15. Grafy: `LineChart` (SVG) pro výsledky, prohlížeč záznamu pro signály. Žádná další knihovna grafů, žádné nové globály `window.*`.

## Zakázáno
16. Stav vyjádřený magickou hodnotou („nezadáno“ = výchozí čísla) – použij výslovný příznak.
17. `except Exception: pass`, zachycení výjimky bez hlášení, záloha stavu přes `ws.__dict__`.
18. Nové závislosti nebo změna verzí bez zadání. Nový kód v `pidtools/desktop` (Qt) – čeká na rozhodnutí TICKET-010.
19. Úpravy mimo „Dotčené soubory“ zadání. Je-li nutná, zastav a napiš proč – jiný agent může soubor právě měnit.
20. Tvrzení o rozhraní bez měření: šířky, počty požadavků a kontrast ověř v prohlížeči (Playwright), ne čtením CSS.

## Postup a odevzdání
21. Jeden úkol = jedna větev `agent/<ID>` z integrační větve; malé commity; žádný PR ani push jinam bez pokynu vlastníka.
22. Nové e2e testy do nového souboru `tests/test_frontend_<id>.py`; stávající testy měň jen kvůli zadané změně chování. Test nikdy nevypínej.
23. Před odevzdáním musí projít: `ruff check pidtools tests`; `cd frontend && npm run lint && npm run typecheck && npm test && npm run build`; `QT_QPA_PLATFORM=offscreen python -m pytest -q` (celé, ne výběr).
24. Zpráva o hotovém úkolu: co je změřeno a jak, co splňuje akceptační kritéria, co ne a proč. Nesplněné kritérium se nezamlčuje.
25. Komentáře v kódu česky, texty rozhraní anglicky + česky, desetinný oddělovač podle jazyka (`useDec`).
