# Návrhy vylepšení PID Tools (listopad 2026)

Stav: **návrh ke schválení**, navazuje na `docs/cs/audit-2026-11.md`. Seřazeno podle poměru dopad / náročnost.
Každé tvrzení o dnešním stavu je ověřené v kódu verze 4.0.0-beta.4 (místo je uvedeno).

---
### [FEATURE-001] Klávesové zkratky a uložení projektu odkudkoli
- **Typ:** Funkční vylepšení
- **Přínos pro uživatele (Proč to dělat):** Ladění říká „New parameters: Calculate (F5)“ (`dk_calc_hint`,
  `dk_stale`), ale ve `frontend/src` je jediná globální klávesa F1 (`components/Guide.tsx:158`). F5 tedy znovu načte
  stránku. Uložit projekt jde jen tlačítkem v záložce 6 (`tabs/ProjectTab.tsx:154`); hlavička ukazuje „saved 07:59 •“,
  ale uložit z ní nejde.
- **Náročnost implementace:** Nízká (Quick Win)
- **Návrh řešení (Specifikace pro agenty):**
  1. Nový `frontend/src/shortcuts.ts`: `useShortcuts()` volaný v `App.tsx`, jeden posluchač `keydown` na `window`.
     Zkratky: `Ctrl+S` uložit projekt, `F5` Calculate (jen v záložce Ladění; jinde nic, ale vždy `preventDefault`),
     `Ctrl+1 … Ctrl+6` záložky (`NAV_TABS`), `Alt+↑ / Alt+↓` předchozí / další smyčka (`PUT /loops/active`),
     `Ctrl+P` záložka Projekt + vytvoření protokolu. Zkratky bez Ctrl / Alt se nespouští, když je fokus v `input`,
     `textarea`, `select`.
  2. Uložení: funkci `save()` z `ProjectTab.tsx` přesuň do `start/project.ts` jako `saveProject()` a použij ji
     v záložce i ve zkratce. Do hlavičky vedle ukazatele uložení (`Header.tsx`, `data-testid="data-sum"`) přidej
     tlačítko „Save“ (primární, když je `dirty`).
  3. Calculate: `useCalc()` (`TuningTab.tsx:249`) zpřístupni přes úložiště `useTun` (`tuningState.ts`) jako akci
     `calc`, aby ji zkratka mohla zavolat mimo komponentu.
  4. Přehled zkratek: text `dk_keys_body` (dnes ho používá jen Qt) uprav podle skutečných zkratek a zobraz ho
     v průvodci (F1) jako kartu „Keyboard“; do `title` tlačítek doplň zkratku.
- **Akceptační kritéria:** E2E: `F5` v Ladění spustí výpočet a stránka se nenačte znovu (ID prostoru i stav
  zůstanou); `Ctrl+S` s neuloženou změnou přepne ukazatel v hlavičce na uloženo; `Ctrl+3` otevře Ladění;
  psaní „1“ do číselného pole nepřepne záložku. Karta zkratek v průvodci odpovídá implementaci.

---
### [FEATURE-002] Kopírování parametrů a tabulek do schránky
- **Typ:** Funkční vylepšení
- **Přínos pro uživatele (Proč to dělat):** Výsledek ladění se přepisuje ručně do faceplatu nebo do e-mailu. Export
  pro řídicí systém existuje jen jako soubor (`TuningProfile.tsx:226`, formáty csv / pcs7 / tia / deltav). Schránka
  se ve `frontend/src` nepoužívá nikde (0 výskytů `clipboard`).
- **Náročnost implementace:** Nízká (Quick Win)
- **Návrh řešení (Specifikace pro agenty):**
  1. `frontend/src/lib/clipboard.ts`: `copyText(text)` (`navigator.clipboard.writeText`, záloha přes skrytý
     `textarea`) a `tableToTsv(table: HTMLTableElement)`.
  2. Karta „Proposal and sets in the PLC“ (`TuningTab.tsx`): u sloupců Suggestion, Set 1, Set 2 ikona „Copy“.
     Kopíruje hodnoty v názvech a jednotkách bloku z `SetInfo.values` (API je už posílá), např.
     `LIC101 · PIDConL: Gain = -2; TI = 200 s; TD = 0 s`, s desetinným oddělovačem jazyka.
  3. Komponenta `Card` dostane volitelnou akci „Copy table“ (TSV pro Excel): zapni u „Quality indicators“,
     „All methods for this model“, tabulky robustnosti, „Transfer type comparison“ (Model) a výsledků APC.
  4. Po zkopírování krátké potvrzení v oblasti `aria-live` (po TICKET-003 z auditu toast).
- **Akceptační kritéria:** E2E s oprávněním schránky: po kliknutí na „Copy“ u Setu 1 obsahuje schránka název
  smyčky, název bloku a tři parametry s jednotkami; „Copy table“ u ukazatelů kvality dá TSV se stejným počtem řádků
  jako tabulka. Tlačítka mají `aria-label` a fungují klávesnicí.

---
### [FEATURE-003] Stav postupu na záložkách a „Další krok“
- **Typ:** UX Workflow
- **Přínos pro uživatele (Proč to dělat):** Postup Data → Model → Ladění → Simulace → APC → Protokol je vidět jen
  jako číslované záložky bez stavu. Kontrolní seznam s položkami `ok / warn / todo` a akcí „přejdi na prvek“ už API
  počítá pro každou záložku (`GET /guide/{tab}`, `api/guide.py: GuideCheck`, `GuideAction`), ale je schovaný
  v průvodci pod F1. Uživatel musí sám vědět, co ještě chybí.
- **Náročnost implementace:** Střední
- **Návrh řešení (Specifikace pro agenty):**
  1. API: `GET /workspaces/{wid}/guide/status` → `{tabs: {data: {ok, warn, todo}, model: …}, next: {tab, text,
     action} | null}`. Počítá se ze stejného `GuideState` jako průvodci (`app/guides.py`), `next` = první položka
     `todo` nebo `warn` v pořadí záložek.
  2. Záložky (`Header.tsx`, `NAV_TABS`): za názvem značka `✓` (vše splněno), `!` (aspoň jedno varování), nic
     (ještě neprovedeno); `title` a `aria-label` se shrnutím „2 of 5 done, 1 warning“.
  3. Řádek kontextu (`components/ContextRow.tsx`): vpravo „Next: <text> [Open]“; tlačítko použije existující
     mechanismus akce průvodce (přepnutí záložky + zvýraznění prvku podle `data-testid`).
  4. Dotaz zařaď do zneplatnění po změnách prostoru jako ostatní (`useWsQuery("guide-status", "/guide/status")`).
- **Akceptační kritéria:** Test API: prázdný prostor → `next.tab == "data"`; po ukázkových datech a identifikaci →
  `tabs.model.todo == 0` a `next` míří do Ladění. E2E: po identifikaci má záložka Model značku `✓`; klik na
  „Open“ přepne na cílovou záložku a prvek dostane třídu `guide-pulse`.

---
### [FEATURE-004] Odečet hodnot a export u všech grafů `LineChart`
- **Typ:** UI Polish
- **Přínos pro uživatele (Proč to dělat):** `components/LineChart.tsx` (grafy APC, diagnostiky, frekvenční
  charakteristiky a validace modelu) nemá žádnou obsluhu ukazatele – hodnotu z grafu nejde
  odečíst ani vyexportovat. Odečet umí jen graf scénáře v Ladění (tlačítko „Measure“) a prohlížeč záznamu.
- **Náročnost implementace:** Střední
- **Návrh řešení (Specifikace pro agenty):**
  1. `LineChart`: při pohybu ukazatele svislá čára a plovoucí tabulka „x + hodnota každé řady“ (nejbližší vzorek,
     u `logX` v logaritmu); klik čáru připíchne, druhý klik přidá druhou čáru a tabulka ukáže Δx a Δy; Esc smaže.
     Šipky ← / → posouvají připíchnutou čáru o vzorek (graf dostane `tabIndex={0}`).
  2. Nabídka v rohu grafu (ikona „⋯“): „Copy data (TSV)“, „Save CSV“, „Save PNG“ (SVG → canvas → PNG, barvy
     z vypočtených stylů). Použij `lib/clipboard.ts` z FEATURE-002.
  3. Klik na položku legendy řadu skryje / zobrazí.
  4. Vše uvnitř komponenty, rozhraní vlastností se nemění; nová vlastnost `tools?: boolean` (výchozí zapnuto).
- **Akceptační kritéria:** Vitest: pohyb ukazatele nad známými daty zobrazí správné hodnoty; dvě čáry dají správné
  Δ. E2E v APC › Feedforward: tabulka odečtu se objeví, CSV má sloupec na každou viditelnou řadu. Bez regresí
  rozměrů grafů ve stávajících e2e testech.

---
### [FEATURE-005] Model: rozdělit dlouhou stránku do tří podzáložek
- **Typ:** UX Workflow
- **Přínos pro uživatele (Proč to dělat):** Záložka Model má při 1 440 × 900 výšku 3 139 px (měřeno): grafy úseků,
  porovnání typů přenosu, validace, simulace, souhrn shody, nejistota, rezidua. Mezi nastavením úseku nahoře
  a rezidui dole se roluje přes tři obrazovky a pravý panel s parametry přitom zůstává stejný.
- **Náročnost implementace:** Střední
- **Návrh řešení (Specifikace pro agenty):**
  1. Podzáložky podle vzoru Data (`store.ts: DATA_SUBS`, `Header.tsx` – `nav.subtabs`): `modelSub` =
     `ident` (grafy s úseky, přehled, porovnání typů přenosu), `validate` (validace, porovnání a simulace),
     `residuals` (souhrn shody, rezidua, nejistota). Uložit do `localStorage` jako `pid.msub`.
  2. `tabs/ModelTab.tsx`: `ModelMain` vykreslí jen komponenty zvolené podzáložky (`ModelTable`, `ModelViews`,
     `ModelDetails`, `ModelValidation`, `ModelResiduals` už jsou oddělené).
  3. Nad podzáložkami stálý pruh se souhrnem vybraného modelu: typ, FIT, hodnocení, stav validace – aby byl
     výsledek vidět ve všech třech pohledech.
  4. Pravý panel: v `validate` a `residuals` sbal karty identifikace (`defaultOpen={false}`), ponech „Model
     validation“ a „Use the model for tuning“.
  5. Akce průvodce, které míří na prvky Modelu, musí přepnout i podzáložku (mapa `data-testid` → `modelSub`).
- **Akceptační kritéria:** Výška obsahu žádné podzáložky Modelu nepřesáhne při 1 440 × 900 dvě obrazovky.
  Stávající e2e (`tests/test_frontend_model.py`) procházejí po doplnění přepnutí podzáložky. Po znovunačtení
  zůstane zvolená podzáložka.

---
### [FEATURE-006] Zpět / znovu pro změny nastavení smyčky
- **Typ:** Funkční vylepšení
- **Přínos pro uživatele (Proč to dělat):** Při zkoušení variant (rozsahy, filtr, sady, scénář) se nejde vrátit
  o krok. Existuje jen ruční snímek v deníku a historie zapsaných ladění (karta „Tuning history“). Omylem přepsaný
  Set 1 nebo úsek identifikace znamená zadat hodnoty znovu.
- **Náročnost implementace:** Střední
- **Návrh řešení (Specifikace pro agenty):**
  1. Server (`app/workspace/loops.py: Project`): zásobník `undo` (max. 50 kroků) a `redo`. Krok = `{label, loop,
     before: {klíč: hodnota}, after: {…}, rng_before, rng_after}`. Zapisuje se v `patch_settings`
     (`api/data.py`), `PUT /tuning/sets/{n}`, `PUT /range` a `PUT /scenario`; po sobě jdoucí změny téhož klíče do
     2 s se sloučí. Načtení dat, změna sloupců a identifikace zásobník vyprázdní (stav modelu se nevrací).
  2. API: `GET /undo` → `{undo: label | null, redo: label | null}`, `POST /undo`, `POST /redo` (vrací
     `WorkspaceInfo`). Návrat projde stejnou kontrolou hodnot jako běžná změna (TICKET-001 z auditu).
  3. UI: v hlavičce dvě tlačítka se `title` „Undo: Set 1 Gain −2 → −1.5“; zkratky `Ctrl+Z` / `Ctrl+Y` přes
     `shortcuts.ts` z FEATURE-001 (ne při fokusu v textovém poli – tam platí vracení prohlížeče).
  4. Zásobník se neukládá do projektu a zaniká s pracovním prostorem.
- **Akceptační kritéria:** Test API: tři změny → tři `POST /undo` vrátí původní `GET /settings`; `redo` je obnoví;
  nová změna po `undo` smaže `redo`; identifikace zásobník vyprázdní. E2E: změna Set 1 Gain, `Ctrl+Z` → pole
  i graf odezvy se vrátí. Zlaté případy beze změny.

---
### [FEATURE-007] Přehled projektu s hromadnými akcemi nad smyčkami
- **Typ:** Funkční vylepšení
- **Přínos pro uživatele (Proč to dělat):** U projektu s více smyčkami se dnes každá smyčka vybere v hlavičce
  a projde zvlášť (identifikace, výpočet, export). Souhrn všech smyček přitom API už má: `GET /loops/overview`
  vrací pro každou model, parametry, Set 1, Set 2 a stav (`api/audit.py: LoopRow`); úlohy s průběhem a rušením
  existují (`app/jobs.py`), export sad pro řídicí systém také, ale jen po jedné sadě.
- **Náročnost implementace:** Vysoká
- **Návrh řešení (Specifikace pro agenty):**
  1. Záložka Projekt: karta „Loops in the project“ – tabulka se sloupci smyčka, PV / MV, model + FIT, Set 1 →
     Set 2 (změna v %), Ms, stav (data / model / návrh / zapsáno do Setu 2), zaškrtávací pole. Klik na řádek
     přepne aktivní smyčku. Zdroj: `/loops/overview`, doplněný o `fit`, `ms` a `set2_defined`.
  2. Hromadné akce nad vybranými: „Identify“ (výchozí nastavení každé smyčky), „Tune“ (metoda a kritérium
     z dialogu, výsledek jen jako návrh – do Setu 2 se zapisuje samostatnou akcí „Accept proposals“), „Export
     sets“ (jeden soubor ve formátu csv / pcs7 / tia / deltav se všemi smyčkami).
  3. Server: `POST /batch` `{loops: [index], action, params}` → jedna úloha; smyčky se zpracují postupně nad
     `lean()` kopiemi, průběh „3 / 12 · FIC100“, zrušení zachová hotové. Výsledek na smyčku: `ok | skipped
     (důvod) | error (text)` – smyčka bez použitelného úseku se přeskočí s důvodem z kontrol kvality dat.
  4. Po dokončení souhrn v kartě (kolik ok / přeskočeno / chyba) a filtr tabulky na problémové řádky.
- **Akceptační kritéria:** Test API: projekt se 3 smyčkami, z toho jedna bez MV → `Identify` vrátí 2× ok a 1×
  skipped s důvodem; žádná smyčka nezmění Set 2 bez „Accept proposals“. Hromadný export obsahuje řádek na každou
  vybranou smyčku a projde stejným testem formátu jako export jedné sady. E2E: průběh je vidět ve stavovém
  řádku a úloha jde zrušit.
