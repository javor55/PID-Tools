"""Doplňkové texty (v4) – slučují se do TEXTS v i18n.py."""

CS = {
    # obecné
    "tab5": "5 · Diagnostika", "tab6": "6 · Plán testu", "tab7": "7 · Kaskáda", "tab8": "8 · Projekt a report",
    "no": "ne", "yes_period": "ano, perioda {p} s",
    "guide_title": "Jak postupovat",
    "guide_body": (
        "1. **Data** – nahraj export, v panelu vyber sloupce PV, MV (a SP, poruchy) a zadej normovací rozsahy jako v bloku.\n"
        "2. **Úsek** – v záložce Data vyber úsek s výraznými změnami MV (skoky v ručním režimu nebo skoky SP v automatu).\n"
        "3. **Model** – spusť identifikaci, vyber model s dobrou shodou, podívej se na rezidua a případně spočítej nejistotu.\n"
        "4. **Ladění** – přečti doporučení PI/PID, otevři porovnání metod, vyber nastavení s nízkým IAE při Ms 1,4–1,8.\n"
        "5. **Ověření** – zkontroluj model na jiném úseku a simulaci smyčky se současnými parametry.\n"
        "6. **Diagnostika** – před přeladěním vyluč stikci ventilu a nelinearitu, po přeladění porovnej výkon před/po.\n"
        "7. **Projekt a report** – ulož projekt smyčky a vygeneruj report pro dokumentaci.\n\n"
        "Nemáš vhodná data? Záložka **Plán testu** navrhne skokový test."),
    "gloss_title": "Glosář",
    "gloss_body": (
        "- **PV / SP / MV** – regulovaná veličina / žádaná hodnota / výstup regulátoru (ventil).\n"
        "- **K, Ki** – zesílení procesu: o kolik % se změní PV na 1 % MV (u integračních procesů rychlost změny za sekundu).\n"
        "- **T1, T2** – časové konstanty (setrvačnost), **θ** – dopravní zpoždění (mrtvý čas).\n"
        "- **θ/(θ+T)** – normalizované zpoždění; rozhoduje o obtížnosti regulace a přínosu D složky.\n"
        "- **Gain, TI, TD** – parametry PIDConL v ideálním tvaru; **DiffGain** – filtr D složky (zpoždění TD/DiffGain).\n"
        "- **τc / λ** – požadovaná rychlost uzavřené smyčky (menší = rychlejší, ale méně robustní).\n"
        "- **Ms** – robustnost (max. citlivost); 1,4 velmi robustní, 2 hraniční. **GM / PM** – amplitudová a fázová bezpečnost.\n"
        "- **IAE** – integrál absolutní regulační odchylky; menší = lepší regulace.\n"
        "- **FF** – dopředná vazba z měřené poruchy; **lead-lag** – její dynamická korekce.\n"
        "- **Harrisův index** – poměr dosažitelného minima rozptylu a skutečného rozptylu (1 = na hranici možností).\n"
        "- **Stikce** – ventil se „lepí“: pohne se až po určité změně MV, pak skočí; způsobuje kmitání, které přeladěním nezmizí."),
    # projekt
    "sb_project": "Projekt smyčky", "loop_tag": "Tag / název smyčky",
    "h_loop_tag": "Použije se v názvu souborů projektu a reportu.",
    "proj_load": "Otevřít projekt (.json)", "h_proj_load": "Obnoví nastavení, model, parametry a případně i data uložená v projektu.",
    "proj_help": "Projekt ukládáš v záložce 8 · Projekt a report.",
    "err_proj": "Projekt nejde načíst: {ex}", "src_project": "Projekt",
    "proj_data_caption": "Data z projektu ({n} vzorků).",
    "proj_title": "Uložit projekt", "proj_save": "Stáhnout projekt (.json)",
    "proj_save_help": "Uloží tag, výběr sloupců, rozsahy, úseky, modely včetně úprav, ladění, FF a současné i nové parametry.",
    "proj_include_data": "Uložit i data", "h_proj_inc": "Projekt pak jde otevřít bez původního exportu (převzorkovaná data).",
    # report
    "rep_title": "Report ladění", "rep_author": "Zpracoval", "rep_comment": "Poznámka do reportu",
    "rep_help": "HTML report s parametry, tabulkami a interaktivními grafy (funguje i offline). Do PDF ho převedeš tiskem z prohlížeče.",
    "rep_build": "Vytvořit report", "rep_dl": "Stáhnout report (HTML)",
    "rep_sec_data": "Data a nastavení", "rep_sec_tuning": "Model a ladění", "rep_sec_diag": "Diagnostika",
    "rep_fig_data": "Data", "rep_fig_model": "Model vs. data", "rep_fig_sim": "Simulace současné a nové nastavení",
    "rep_fig_val": "Ověření", "rep_tab_models": "Identifikované modely", "rep_tab_tuning": "Současné a nové parametry",
    "rep_tab_kpi": "Ukazatele simulace", "rep_val_pred": "Ověření na jiném úseku: shoda predikce PV {f} %.",
    "rep_osc": "Oscilace s periodou {p} s, Horchův poměr {r}.", "rep_hyst": "Odhad vůle/hystereze ventilu: {h} {u}.",
    "rep_nl": "Rozptyl lokálních zesílení (max/min): {s}.",
    # nápovědy – postranní panel
    "h_source": "Soubor = vlastní export, Ukázka = simulovaná nádrž pro vyzkoušení, Projekt = data uložená v projektu.",
    "h_pv": "Regulovaná veličina (měření), např. hladina.", "h_mv": "Výstup regulátoru – žádaná poloha ventilu.",
    "h_sp": "Žádaná hodnota. Nutná pro simulaci smyčky na záznamu a pro ukazatele výkonu.",
    "col_pos": "Poloha ventilu (nepovinné)", "h_pos": "Měřená skutečná poloha ventilu – umožní přímo odhadnout vůli a stikci.",
    "h_ts_manual": "Použij, když časové značky neodpovídají skutečnému vzorkování (např. export z archivu).",
    "h_normpv": "Rozsah PV v bloku (NormPV) – obvykle měřicí rozsah. Určuje, jak se přepočítává Gain.",
    "h_normmv": "Rozsah MV v bloku (NormMV), typicky 0–100 %.",
    "h_unit": "Jednotka jen pro popisky os a tabulek.",
    "h_dfb": "D složka počítaná jen z PV – skok SP nevyvolá derivační ráz. Obvykle doporučeno.",
    "h_deadband": "Pásmo necitlivosti regulační odchylky v jednotkách PV. 0 = vypnuto.",
    "h_mvlim": "Omezení výstupu regulátoru (MV_HiLim, MV_LoLim) – v simulaci včetně anti-windupu.",
    "h_current": "Parametry, se kterými smyčka běží teď – slouží k porovnání a k ověření modelu na záznamu z automatu.",
    "h_gain": "Zesílení regulátoru (bezrozměrné při normování). Záporné = opačný smysl působení.",
    "h_ti": "Integrační časová konstanta v sekundách. Menší = silnější integrace.",
    "h_td": "Derivační časová konstanta v sekundách. 0 = bez D složky.",
    "h_plot_h": "Výška hlavních grafů v pixelech.",
    # nápovědy – data, model, ladění
    "h_seg_id": "Časový úsek, ze kterého se model identifikuje. Lze ho vybrat i tažením myší v grafu.",
    "h_mouse": "Přiblížit = tažením zvětšíš část grafu. Vybrat úsek = tažením nastavíš úsek pro identifikaci.",
    "h_models": "Struktury modelů, které se nafitují a porovnají. Integrační volit u hladin s vnuceným odtokem.",
    "h_model_for_tuning": "Model, ze kterého se počítá ladění, diagnostika a plán testu.",
    "h_dist_0": "Zesílení poruchy (u integračních rychlost změny PV na jednotku poruchy).",
    "h_dist_1": "Časová konstanta působení poruchy [s].", "h_dist_2": "Dopravní zpoždění poruchy [s].",
    "h_resid": "Rozdíl naměřené PV a modelu. Systematický tvar (ne jen šum) znamená, že model něco nevysvětluje.",
    "h_ctype": "PI nebo PID. Doporučení podle modelu je v panelu nahoře.",
    "h_avg_dpv": "O kolik smí hladina uhnout od SP při největší poruše.",
    "opt_robust": "Robustní vůči nejistotě",
    "h_opt_robust_bs": "Podmínka Ms musí platit pro všechny varianty modelu z výpočtu nejistoty (záložka Model).",
    "h_opt_robust_corner": "Podmínka Ms musí platit i pro K ±20 % a θ −20/+30 %. Přesnější je spočítat nejistotu v záložce Model.",
    "note_opt_robust": "Robustní vůči {n} variantám modelu.",
    "h_new_gain": "Navržené zesílení – předvyplněné metodou, lze ručně upravit.",
    "h_ff_use": "Zapne dopřednou vazbu z této měřené poruchy v simulaci.",
    "h_ff_gain": "Statické zesílení FF = −Kd/K. Záporné znamená, že MV jde proti poruše.",
    "ff_dyn": "Dynamická FF (lead-lag)",
    "h_ff_dyn": "Kromě zesílení i časová korekce: (Tlead·s + 1)/(Tlag·s + 1) a zpoždění. Kompenzuje rozdílnou rychlost poruchy a MV.",
    "ff_lead": "Tlead [s]", "ff_lag": "Tlag [s]", "ff_delay": "Zpoždění FF [s]",
    "h_ff_lead": "Předvyplněno časovou konstantou procesu (MV → PV).",
    "h_ff_lag": "Předvyplněno časovou konstantou poruchy (porucha → PV).",
    "h_ff_delay": "Předvyplněno rozdílem θd − θ, pokud porucha působí pomaleji než MV.",
    "ms_worst": "Ms nejhorší z nejistoty",
    "h_robust_on": "Přidá simulaci nového nastavení na procesu s K ×1,3 a θ ×1,5 – test odolnosti.",
    "spread_on": "Rozptyl modelů", "h_spread_on": "Nové nastavení na variantách modelu z výpočtu nejistoty (záložka Model).",
    "h_scenario": "Skoky = umělý test SP a poruch. Naměřené poruchy = přehraje skutečné průběhy z úseku.",
    "h_sim_len": "Délka simulace v sekundách.", "h_sp_step": "Velikost skoku SP v jednotkách PV.",
    "h_d_step": "Skok měřené poruchy v jejích jednotkách (v 70 % simulace).",
    "h_seg_val": "Úsek pro ověření – ideálně jiný než úsek identifikace.",
    "h_val_which": "Současné = ověření modelu (simulace by měla sedět na záznam). Nové = co by se stalo s novým laděním.",
    # nejistota
    "unc_title": "Nejistota modelu",
    "unc_help": "Opakovaný fit na datech s přeskládaným šumem (bootstrap) ukáže, jak přesně jsou parametry určené. "
                "Velký rozptyl znamená, že data parametr dobře neurčují – typicky kompromis mezi T1 a θ.",
    "unc_n": "Počet opakování", "h_unc_n": "Víc opakování = přesnější odhad, ale delší výpočet (cca 1 s na opakování).",
    "unc_run": "Spočítat nejistotu", "unc_running": "Počítám nejistotu…",
    "unc_nominal": "Model", "unc_p05": "5 %", "unc_p95": "95 %", "unc_rel": "Rozptyl",
    "unc_variants": "varianty", "unc_after": "Varianty se použijí pro robustní optimalizaci a rozptyl v simulaci (záložka Ladění).",
    # diagnostika
    "diag_intro": "Vyber úsek provozních dat (typicky smyčka v automatu). Ukazatele výkonu, detekce oscilací a stikce "
                  "pracují s tímto úsekem, kontrola nelinearity s úsekem identifikace.",
    "seg_diag": "Úsek pro diagnostiku [s]", "h_seg_diag": "Úsek provozních dat, který se hodnotí.",
    "diag_integ": "Integrační proces", "h_diag_integ": "Mění test stikce: u integračních procesů se porovnává MV s rychlostí změny PV.",
    "diag_theta": "Dopravní zpoždění [s]", "h_diag_theta": "Potřebné pro Harrisův index, když není nafitovaný model.",
    "perf_title": "Výkon smyčky", "perf_compare": "Porovnat se druhým úsekem",
    "h_perf_compare": "Např. před a po přeladění.", "seg_diag_b": "Úsek B [s]", "seg_a": "Úsek A", "seg_b": "Úsek B",
    "kpi_std": "Směr. odchylka reg. odchylky [{u}]", "kpi_iae_h": "IAE za hodinu [{u}·s/h]",
    "kpi_travel_h": "Pohyb MV za hodinu [{u}/h]", "kpi_rev_h": "Změny směru MV za hodinu", "kpi_at_lim": "MV v limitu",
    "kpi_harris": "Harrisův index", "kpi_osc": "Oscilace",
    "perf_help": "Pohyb a změny směru MV měří namáhání ventilu. Harrisův index blízko 1 = regulace je na hranici "
                 "možností daných zpožděním; pod 0,3–0,5 bývá prostor ke zlepšení (ladění, FF, šum).",
    "osc_title": "Oscilace a ventil", "osc_none": "Pravidelná oscilace nebyla v úseku zjištěna.",
    "osc_found": "Zjištěna pravidelná oscilace: perioda {p} s, amplituda ≈ {a} {u} (pravidelnost {r}).",
    "stic_likely": "Korelace MV a PV je lichá (poměr {r}) – typický znak stikce ventilu. Přeladění kmitání neodstraní, "
                   "ověř ventil testem malých kroků v ručním režimu.",
    "stic_unlikely": "Korelace MV a PV je sudá (poměr {r}) – oscilaci způsobuje spíš ladění nebo vnější periodická porucha.",
    "stic_unclear": "Korelace MV a PV nedává jasný závěr (poměr {r}). Zkus test v ručním režimu.",
    "ccf": "korelace", "ccf_title": "Vzájemná korelace MV a PV", "ccf_title_d": "Vzájemná korelace MV a dPV/dt",
    "lag_s": "posun [s]", "phase_title": "MV vs. PV",
    "osc_help": "Horchův test: u stikce je korelace kolem nulového posunu nulová (lichá), u špatného ladění má maximum "
                "u nuly (sudá). Test je orientační – potvrzuje se krokovým testem ventilu.",
    "hyst": "Odhad vůle/hystereze ventilu", "h_hyst": "Rozdíl MV při otevírání a zavírání pro stejnou polohu ventilu.",
    "pos_title": "MV vs. poloha ventilu", "pos_missing": "Tip: se sloupcem polohy ventilu aplikace odhadne vůli přímo.",
    "nl_title": "Nelinearita", "nl_few": "Pro kontrolu nelinearity jsou potřeba aspoň dva skoky MV v úseku identifikace.",
    "nl_time": "Čas [s]", "nl_from": "MV z", "nl_to": "MV na", "nl_dir": "Směr", "nl_gain": "Lokální zesílení",
    "nl_ratio": "Poměr k modelu",
    "nl_warn": "Lokální zesílení se liší až {s}× – proces je výrazně nelineární. Jedno ladění nebude sedět všude: "
               "laď na nejvyšší zesílení (robustně), zvaž linearizaci charakteristiky ventilu nebo gain scheduling.",
    "nl_ok": "Lokální zesílení jsou konzistentní (max/min {s}) – lineární model je v tomto rozsahu v pořádku.",
    "nl_dir_warn": "Zesílení při otevírání a zavírání se liší (poměr {r}) – může jít o vůli ventilu nebo o nesymetrický proces.",
    "nl_help": "Pro každý skok MV se dopočítá zesílení, které nejlépe vysvětlí odezvu. Body podle polohy MV ukazují "
               "tvar charakteristiky.",
    # plán testu
    "plan_title": "Plán skokového testu",
    "plan_intro": "Návrh skokového testu v ručním režimu tak, aby dal přesný model a PV přitom nepřekročila povolenou odchylku.",
    "plan_src": "Model", "plan_src_fit": "Z identifikace", "plan_src_manual": "Odhad ručně",
    "h_plan_src": "Bez dat stačí hrubý odhad z provozní zkušenosti.",
    "plan_type": "Typ procesu", "h_plan_k": "Zesílení v %/% (u integračních %/(%·s)).",
    "plan_dpv": "Max. odchylka PV [{u}]", "h_plan_dpv": "O kolik smí PV během testu nejvýš uhnout.",
    "plan_sigma": "Šum PV σ [{u}]", "h_plan_sigma": "Odhad z reziduí modelu, nebo zadej ručně.",
    "plan_snr": "Cílový poměr signál/šum", "h_plan_snr": "Změna PV / šum. 10 a víc dává spolehlivý model.",
    "plan_mv0": "Výchozí MV [{u}]", "h_plan_mv0": "Poloha MV na začátku testu (kvůli limitům).",
    "plan_step": "Velikost skoku [{u}]", "plan_hold": "Držet krok", "plan_total": "Celková doba",
    "plan_snr_ach": "Signál/šum",
    "plan_infeasible": "Při povolené odchylce PV je šum příliš velký – model z testu nebude spolehlivý. Povol větší odchylku "
                       "nebo zlepši měření (filtr).",
    "plan_low_snr": "Poměr signál/šum je pod cílem – model bude méně přesný.",
    "plan_room": "Skok by se nevešel do limitů MV – posuň výchozí MV nebo zmenši skok.",
    "plan_pv": "Očekávaná PV", "plan_at": "Čas od začátku", "plan_set": "Nastav MV [{u}]", "plan_dl": "Stáhnout plán (CSV)",
    "plan_tips_self": ("- Před testem počkej na ustálení a přepni do ručního režimu.\n"
                       "- Dublet nahoru/dolů ukáže i nelinearitu a vůli ventilu.\n"
                       "- Během testu hlídej neměřené poruchy – když přijdou, krok zopakuj.\n"
                       "- Po testu nahraj export a model nafituj na celý test."),
    "plan_tips_integ": ("- Hladina se během pulzů nevrací sama – sleduj ji a při přiblížení k limitu vrať MV.\n"
                        "- Pulzy nahoru/dolů hladinu vrací zpět, proto se dají opakovat.\n"
                        "- Alternativa: v automatu udělej skoky SP (bezpečnější pro integrační procesy).\n"
                        "- Pokud je měřený přítok, zahrň ho jako poruchu – model bude přesnější."),
    # kaskáda
    "cas_intro": "Kaskáda: vnější regulátor (tvůj model, např. hladina) nastavuje SP vnitřní smyčky (např. průtok), "
                 "ta řídí ventil. **MV v datech hlavního modelu musí být SP vnitřní smyčky v % jejího rozsahu.**",
    "cas_inner": "Vnitřní smyčka", "cas_src": "Model vnitřní smyčky", "cas_src_data": "Z dat", "cas_src_manual": "Ručně",
    "h_cas_src": "Z dat = identifikace ze sloupců v souboru (stejný úsek jako hlavní model).",
    "cas_ipv": "PV vnitřní smyčky", "cas_imv": "MV vnitřní smyčky (ventil)",
    "h_cas_ipv": "Např. průtok.", "h_cas_imv": "Výstup vnitřního regulátoru (normovaný jako MV v panelu).",
    "cas_ilo": "Rozsah PV Low", "cas_ihi": "Rozsah PV High", "h_cas_irange": "Normovací rozsah PV vnitřní smyčky.",
    "cas_fit": "Identifikovat vnitřní smyčku", "cas_inner_fit": "{m}, shoda {f} %: {p}",
    "h_cas_k": "Zesílení vnitřního procesu v %/%.",
    "cas_need_inner": "Zadej nebo identifikuj model vnitřní smyčky.",
    "cas_inner_tune": "Ladění vnitřní smyčky", "cas_samp": "SampleTime vnitřní [s]",
    "cas_t63": "Odezva vnitřní smyčky (63 %)", "h_cas_t63": "Za jak dlouho dosáhne vnitřní PV 63 % skoku SP.",
    "cas_outer_tune": "Ladění vnější smyčky",
    "cas_outer_model": "Vnější model včetně uzavřené vnitřní smyčky: {m} – {p}",
    "cas_sep": "Oddělení rychlostí", "h_cas_sep": "Poměr rychlosti vnější a vnitřní smyčky. Doporučeno aspoň 4–5×.",
    "cas_sep_warn": "Vnější smyčka není dost pomalejší než vnitřní (< 4×) – smyčky se mohou navzájem rozkmitat. "
                    "Zpomal vnější nebo zrychli vnitřní smyčku.",
    "cas_pv_o": "PV vnější", "cas_sp_i": "SP vnitřní", "cas_pv_i": "PV vnitřní", "cas_valve": "ventil",
    "cas_inner_pct": "vnitřní [%]", "cas_valve_pct": "ventil [%]",
    "cas_sim_help": "Skok vnějšího SP, pak porucha na ventilu (vnitřní smyčka ji má potlačit sama) a porucha na vnějším procesu.",
}

EN = {
    "tab5": "5 · Diagnostics", "tab6": "6 · Test plan", "tab7": "7 · Cascade", "tab8": "8 · Project & report",
    "no": "no", "yes_period": "yes, period {p} s",
    "guide_title": "How to proceed",
    "guide_body": (
        "1. **Data** – upload an export, select PV, MV (and SP, disturbances) in the sidebar and set scaling ranges as in the block.\n"
        "2. **Segment** – in the Data tab select a segment with clear MV changes (manual steps or SP steps in auto).\n"
        "3. **Model** – run the identification, pick a model with a good fit, check residuals and optionally compute uncertainty.\n"
        "4. **Tuning** – read the PI/PID recommendation, open the method comparison, pick a setting with low IAE at Ms 1.4–1.8.\n"
        "5. **Validation** – check the model on another segment and simulate the loop with the current parameters.\n"
        "6. **Diagnostics** – rule out valve stiction and nonlinearity before retuning; compare performance before/after.\n"
        "7. **Project & report** – save the loop project and generate a report for documentation.\n\n"
        "No suitable data? The **Test plan** tab designs a step test."),
    "gloss_title": "Glossary",
    "gloss_body": (
        "- **PV / SP / MV** – process value / setpoint / controller output (valve).\n"
        "- **K, Ki** – process gain: % change of PV per 1 % MV (for integrating processes the rate of change per second).\n"
        "- **T1, T2** – time constants (lag), **θ** – dead time.\n"
        "- **θ/(θ+T)** – normalized dead time; determines how hard the loop is and how much D helps.\n"
        "- **Gain, TI, TD** – PIDConL parameters in ideal form; **DiffGain** – derivative filter (lag TD/DiffGain).\n"
        "- **τc / λ** – desired closed-loop speed (smaller = faster but less robust).\n"
        "- **Ms** – robustness (max. sensitivity); 1.4 very robust, 2 borderline. **GM / PM** – gain and phase margin.\n"
        "- **IAE** – integral of absolute control error; lower = better.\n"
        "- **FF** – feedforward from a measured disturbance; **lead-lag** – its dynamic correction.\n"
        "- **Harris index** – ratio of achievable minimum variance to actual variance (1 = at the limit).\n"
        "- **Stiction** – the valve sticks: it moves only after a certain MV change, then jumps; causes oscillation that retuning won't remove."),
    "sb_project": "Loop project", "loop_tag": "Tag / loop name",
    "h_loop_tag": "Used in project and report file names.",
    "proj_load": "Open project (.json)", "h_proj_load": "Restores settings, model, parameters and optionally the data stored in the project.",
    "proj_help": "Save the project in tab 8 · Project & report.",
    "err_proj": "Cannot load the project: {ex}", "src_project": "Project",
    "proj_data_caption": "Data from the project ({n} samples).",
    "proj_title": "Save project", "proj_save": "Download project (.json)",
    "proj_save_help": "Saves tag, column selection, ranges, segments, models incl. edits, tuning, FF and current and new parameters.",
    "proj_include_data": "Include data", "h_proj_inc": "The project can then be opened without the original export (resampled data).",
    "rep_title": "Tuning report", "rep_author": "Prepared by", "rep_comment": "Note for the report",
    "rep_help": "HTML report with parameters, tables and interactive charts (works offline). Print it to PDF from the browser.",
    "rep_build": "Create report", "rep_dl": "Download report (HTML)",
    "rep_sec_data": "Data and settings", "rep_sec_tuning": "Model and tuning", "rep_sec_diag": "Diagnostics",
    "rep_fig_data": "Data", "rep_fig_model": "Model vs. data", "rep_fig_sim": "Simulation of current and new tuning",
    "rep_fig_val": "Validation", "rep_tab_models": "Identified models", "rep_tab_tuning": "Current and new parameters",
    "rep_tab_kpi": "Simulation indicators", "rep_val_pred": "Validation on another segment: PV prediction fit {f} %.",
    "rep_osc": "Oscillation with period {p} s, Horch ratio {r}.", "rep_hyst": "Estimated valve backlash/hysteresis: {h} {u}.",
    "rep_nl": "Spread of local gains (max/min): {s}.",
    "h_source": "File = your export, Demo = simulated tank to try things out, Project = data stored in a project.",
    "h_pv": "Controlled variable (measurement), e.g. level.", "h_mv": "Controller output – requested valve position.",
    "h_sp": "Setpoint. Required for loop simulation on recorded data and for performance indicators.",
    "col_pos": "Valve position (optional)", "h_pos": "Measured actual valve position – enables direct estimation of backlash and stiction.",
    "h_ts_manual": "Use when timestamps do not match the actual sampling (e.g. archive export).",
    "h_normpv": "PV range in the block (NormPV) – usually the measuring range. Determines how Gain is scaled.",
    "h_normmv": "MV range in the block (NormMV), typically 0–100 %.",
    "h_unit": "Unit for axis and table labels only.",
    "h_dfb": "D action computed from PV only – an SP step causes no derivative kick. Usually recommended.",
    "h_deadband": "Dead band of the control error in PV units. 0 = off.",
    "h_mvlim": "Controller output limits (MV_HiLim, MV_LoLim) – simulated incl. anti-windup.",
    "h_current": "Parameters the loop runs with now – used for comparison and for validating the model on auto-mode data.",
    "h_gain": "Controller gain (dimensionless with scaling). Negative = reverse action.",
    "h_ti": "Integral time in seconds. Smaller = stronger integral action.",
    "h_td": "Derivative time in seconds. 0 = no D action.",
    "h_plot_h": "Height of the main charts in pixels.",
    "h_seg_id": "Time segment used for identification. Can also be selected by dragging in the chart.",
    "h_mouse": "Zoom = drag to enlarge a part of the chart. Select segment = drag to set the identification segment.",
    "h_models": "Model structures to fit and compare. Choose integrating for levels with forced outflow.",
    "h_model_for_tuning": "Model used for tuning, diagnostics and the test plan.",
    "h_dist_0": "Disturbance gain (for integrating models the PV rate per disturbance unit).",
    "h_dist_1": "Disturbance time constant [s].", "h_dist_2": "Disturbance dead time [s].",
    "h_resid": "Difference between measured PV and the model. A systematic shape (not just noise) means the model misses something.",
    "h_ctype": "PI or PID. The model-based recommendation is shown in the panel above.",
    "h_avg_dpv": "How far the level may move from SP for the largest disturbance.",
    "opt_robust": "Robust to uncertainty",
    "h_opt_robust_bs": "The Ms condition must hold for all model variants from the uncertainty analysis (Model tab).",
    "h_opt_robust_corner": "The Ms condition must also hold for K ±20 % and θ −20/+30 %. Computing the uncertainty in the Model tab is more accurate.",
    "note_opt_robust": "Robust to {n} model variants.",
    "h_new_gain": "Suggested gain – prefilled by the method, can be edited.",
    "h_ff_use": "Enables feedforward from this measured disturbance in the simulation.",
    "h_ff_gain": "Static FF gain = −Kd/K. Negative means MV moves against the disturbance.",
    "ff_dyn": "Dynamic FF (lead-lag)",
    "h_ff_dyn": "Besides the gain also a time correction: (Tlead·s + 1)/(Tlag·s + 1) and delay. Compensates different speeds of the disturbance and MV.",
    "ff_lead": "Tlead [s]", "ff_lag": "Tlag [s]", "ff_delay": "FF delay [s]",
    "h_ff_lead": "Prefilled with the process time constant (MV → PV).",
    "h_ff_lag": "Prefilled with the disturbance time constant (disturbance → PV).",
    "h_ff_delay": "Prefilled with θd − θ if the disturbance acts slower than the MV.",
    "ms_worst": "Worst Ms over uncertainty",
    "h_robust_on": "Adds a simulation of the new tuning on a process with K ×1.3 and θ ×1.5 – robustness test.",
    "spread_on": "Model spread", "h_spread_on": "New tuning on the model variants from the uncertainty analysis (Model tab).",
    "h_scenario": "Steps = synthetic SP and disturbance test. Measured disturbances = replays real signals from the segment.",
    "h_sim_len": "Simulation length in seconds.", "h_sp_step": "Size of the SP step in PV units.",
    "h_d_step": "Step of the measured disturbance in its units (at 70 % of the simulation).",
    "h_seg_val": "Validation segment – ideally different from the identification segment.",
    "h_val_which": "Current = model validation (simulation should match the record). New = what would happen with the new tuning.",
    "unc_title": "Model uncertainty",
    "unc_help": "Repeated fits on data with reshuffled noise (bootstrap) show how accurately the parameters are determined. "
                "A large spread means the data does not pin the parameter down – typically a trade-off between T1 and θ.",
    "unc_n": "Repetitions", "h_unc_n": "More repetitions = more accurate estimate but longer computation (about 1 s each).",
    "unc_run": "Compute uncertainty", "unc_running": "Computing uncertainty…",
    "unc_nominal": "Model", "unc_p05": "5 %", "unc_p95": "95 %", "unc_rel": "Spread",
    "unc_variants": "variants", "unc_after": "The variants are used for robust optimization and model spread in the simulation (Tuning tab).",
    "diag_intro": "Select a segment of operating data (typically the loop in auto). Performance indicators, oscillation and "
                  "stiction detection use this segment; the nonlinearity check uses the identification segment.",
    "seg_diag": "Diagnostics segment [s]", "h_seg_diag": "Operating data segment to evaluate.",
    "diag_integ": "Integrating process", "h_diag_integ": "Changes the stiction test: for integrating processes MV is compared with the rate of change of PV.",
    "diag_theta": "Dead time [s]", "h_diag_theta": "Needed for the Harris index when no model has been fitted.",
    "perf_title": "Loop performance", "perf_compare": "Compare with a second segment",
    "h_perf_compare": "E.g. before and after retuning.", "seg_diag_b": "Segment B [s]", "seg_a": "Segment A", "seg_b": "Segment B",
    "kpi_std": "Std. dev. of control error [{u}]", "kpi_iae_h": "IAE per hour [{u}·s/h]",
    "kpi_travel_h": "MV travel per hour [{u}/h]", "kpi_rev_h": "MV reversals per hour", "kpi_at_lim": "MV at limit",
    "kpi_harris": "Harris index", "kpi_osc": "Oscillation",
    "perf_help": "MV travel and reversals measure valve wear. A Harris index near 1 = control is at the limit set by the "
                 "dead time; below 0.3–0.5 there is usually room for improvement (tuning, FF, noise).",
    "osc_title": "Oscillation and valve", "osc_none": "No regular oscillation detected in the segment.",
    "osc_found": "Regular oscillation detected: period {p} s, amplitude ≈ {a} {u} (regularity {r}).",
    "stic_likely": "The MV–PV correlation is odd (ratio {r}) – a typical sign of valve stiction. Retuning will not remove "
                   "the oscillation; check the valve with small steps in manual mode.",
    "stic_unlikely": "The MV–PV correlation is even (ratio {r}) – the oscillation is more likely caused by tuning or an external periodic disturbance.",
    "stic_unclear": "The MV–PV correlation is inconclusive (ratio {r}). Try a test in manual mode.",
    "ccf": "correlation", "ccf_title": "Cross-correlation of MV and PV", "ccf_title_d": "Cross-correlation of MV and dPV/dt",
    "lag_s": "lag [s]", "phase_title": "MV vs. PV",
    "osc_help": "Horch test: with stiction the correlation around zero lag is zero (odd); with bad tuning it peaks at "
                "zero (even). The test is indicative – confirm with a valve step test.",
    "hyst": "Estimated valve backlash/hysteresis", "h_hyst": "Difference of MV when opening and closing for the same valve position.",
    "pos_title": "MV vs. valve position", "pos_missing": "Tip: with a valve position column the app estimates backlash directly.",
    "nl_title": "Nonlinearity", "nl_few": "The nonlinearity check needs at least two MV steps in the identification segment.",
    "nl_time": "Time [s]", "nl_from": "MV from", "nl_to": "MV to", "nl_dir": "Direction", "nl_gain": "Local gain",
    "nl_ratio": "Ratio to model",
    "nl_warn": "Local gains differ up to {s}× – the process is clearly nonlinear. One tuning will not fit everywhere: "
               "tune for the highest gain (robustly), consider linearizing the valve characteristic or gain scheduling.",
    "nl_ok": "Local gains are consistent (max/min {s}) – a linear model is fine in this range.",
    "nl_dir_warn": "Gain when opening and closing differs (ratio {r}) – possibly valve backlash or an asymmetric process.",
    "nl_help": "For each MV step the gain that best explains the response is computed. Plotted against MV position the points "
               "show the shape of the characteristic.",
    "plan_title": "Step test plan",
    "plan_intro": "Design of a manual-mode step test that gives an accurate model while PV stays within the allowed deviation.",
    "plan_src": "Model", "plan_src_fit": "From identification", "plan_src_manual": "Manual estimate",
    "h_plan_src": "Without data, a rough estimate from operating experience is enough.",
    "plan_type": "Process type", "h_plan_k": "Gain in %/% (for integrating %/(%·s)).",
    "plan_dpv": "Max. PV deviation [{u}]", "h_plan_dpv": "How far PV may move during the test at most.",
    "plan_sigma": "PV noise σ [{u}]", "h_plan_sigma": "Estimated from model residuals, or enter manually.",
    "plan_snr": "Target signal-to-noise ratio", "h_plan_snr": "PV change / noise. 10 or more gives a reliable model.",
    "plan_mv0": "Initial MV [{u}]", "h_plan_mv0": "MV position at the start of the test (for limits).",
    "plan_step": "Step size [{u}]", "plan_hold": "Hold each step", "plan_total": "Total duration",
    "plan_snr_ach": "Signal/noise",
    "plan_infeasible": "With the allowed PV deviation the noise is too large – the model from this test will not be reliable. "
                       "Allow a larger deviation or improve the measurement (filter).",
    "plan_low_snr": "The signal-to-noise ratio is below target – the model will be less accurate.",
    "plan_room": "The step would not fit within the MV limits – move the initial MV or reduce the step.",
    "plan_pv": "Expected PV", "plan_at": "Time from start", "plan_set": "Set MV [{u}]", "plan_dl": "Download plan (CSV)",
    "plan_tips_self": ("- Wait for steady state before the test and switch to manual.\n"
                       "- The up/down doublet also reveals nonlinearity and valve backlash.\n"
                       "- Watch for unmeasured disturbances during the test – repeat the step if one occurs.\n"
                       "- After the test upload the export and fit the model on the whole test."),
    "plan_tips_integ": ("- The level does not return by itself during pulses – watch it and restore MV when approaching a limit.\n"
                        "- Up/down pulses bring the level back, so they can be repeated.\n"
                        "- Alternative: make SP steps in auto (safer for integrating processes).\n"
                        "- If the inflow is measured, include it as a disturbance – the model will be more accurate."),
    "cas_intro": "Cascade: the outer controller (your model, e.g. level) sets the SP of the inner loop (e.g. flow), which "
                 "drives the valve. **The MV in the main model data must be the inner loop SP in % of its range.**",
    "cas_inner": "Inner loop", "cas_src": "Inner loop model", "cas_src_data": "From data", "cas_src_manual": "Manual",
    "h_cas_src": "From data = identification from columns in the file (same segment as the main model).",
    "cas_ipv": "Inner loop PV", "cas_imv": "Inner loop MV (valve)",
    "h_cas_ipv": "E.g. flow.", "h_cas_imv": "Inner controller output (scaled like MV in the sidebar).",
    "cas_ilo": "PV range Low", "cas_ihi": "PV range High", "h_cas_irange": "Scaling range of the inner loop PV.",
    "cas_fit": "Identify inner loop", "cas_inner_fit": "{m}, fit {f} %: {p}",
    "h_cas_k": "Inner process gain in %/%.",
    "cas_need_inner": "Enter or identify the inner loop model.",
    "cas_inner_tune": "Inner loop tuning", "cas_samp": "Inner SampleTime [s]",
    "cas_t63": "Inner loop response (63 %)", "h_cas_t63": "Time for the inner PV to reach 63 % of an SP step.",
    "cas_outer_tune": "Outer loop tuning",
    "cas_outer_model": "Outer model including the closed inner loop: {m} – {p}",
    "cas_sep": "Speed separation", "h_cas_sep": "Ratio of outer to inner loop speed. At least 4–5× recommended.",
    "cas_sep_warn": "The outer loop is not sufficiently slower than the inner loop (< 4×) – the loops may excite each other. "
                    "Slow down the outer or speed up the inner loop.",
    "cas_pv_o": "Outer PV", "cas_sp_i": "Inner SP", "cas_pv_i": "Inner PV", "cas_valve": "valve",
    "cas_inner_pct": "inner [%]", "cas_valve_pct": "valve [%]",
    "cas_sim_help": "Outer SP step, then a disturbance at the valve (the inner loop should reject it) and a disturbance on the outer process.",
}


# v5: kvalita dat, automatické úseky, ukazatel postupu
CS.update({'loading': 'Načítám soubor…', 'auto_title': 'Automaticky nalezené úseky ({n})', 'auto_none': 'V datech nebyly nalezeny výrazné skoky MV ani SP. Úsek vyber ručně nebo si nech navrhnout test v záložce Plán testu.', 'auto_from': 'Od [s]', 'auto_to': 'Do [s]', 'auto_len': 'Délka [min]', 'auto_steps': 'Skoky MV / SP', 'auto_dirs': 'Směry', 'auto_quality': 'Hodnocení', 'auto_use_id': 'Použít pro identifikaci', 'auto_use_val': 'Použít pro ověření', 'auto_help': 'Úseky jsou shluky skoků MV (ruční režim) nebo SP (automat) s časem na ustálení. Vyber řádek a použij ho.', 'auto_gap': 'Max. mezera mezi skoky [s] (0 = auto)', 'h_auto_gap': 'Skoky vzdálenější než tato mezera tvoří samostatné úseky. Automaticky 3× typický odstup skoků.', 'q_title': 'Kvalita dat pro identifikaci', 'q_level0': 'vhodná', 'q_level1': 'použitelná s výhradou', 'q_level2': 'nevhodná', 'q_steps_ok': '{n} výrazných skoků MV/SP.', 'q_steps_one': 'Jen jeden skok – model bude méně spolehlivý, ideálně aspoň 2 oběma směry.', 'q_steps_none': 'Žádný výrazný skok MV ani SP – z úseku nejde model spolehlivě určit.', 'q_one_dir': 'Všechny skoky jsou jedním směrem – přidej skok opačným směrem (odhalí i nelinearitu a vůli).', 'q_snr_ok': 'Poměr signál/šum {s} – dobrý.', 'q_snr_low': 'Poměr signál/šum jen {s} – model bude méně přesný.', 'q_snr_bad': 'Poměr signál/šum {s} – odezva zaniká v šumu.', 'q_lim_warn': 'MV je v limitu {p} % času.', 'q_lim_bad': 'MV je v limitu {p} % času – tam data nenesou informaci o procesu.', 'q_compressed': '{p} % po sobě jdoucích hodnot PV je stejných – archiv je nejspíš komprimovaný.', 'q_sp_ramp': 'SP se mění plynule (rampou) – skoky SP dají přesnější model.', 'q_sampling': 'Perioda dat {h} s je vzhledem k dynamice procesu hrubá.', 'q_fast_steps': 'Nejkratší odstup skoků {g} s je kratší než doba ustálení (~{s} s) – proces se nestihne ustálit.', 'q_short_tail': 'Po posledním skoku chybí čas na ustálení (~{s} s) – prodluž úsek.', 'q_short': 'Úsek je příliš krátký.', 'proj_build': 'Připravit projekt', 'prog_data': 'Data', 'prog_model': 'Model', 'prog_val': 'Ověření', 'prog_tune': 'Ladění', 'prog_diag': 'Diagnostika', 'prog_save': 'Projekt', 'hint_next': 'Další krok', 'hint_data': 'vyber vhodnější úsek (záložka Data – automaticky nalezené úseky) nebo si nech navrhnout test.', 'hint_model_none': 'spusť identifikaci v záložce Model.', 'hint_model_stale': 'úsek nebo nastavení se změnily – spusť identifikaci znovu.', 'hint_model_low': 'shoda modelu je nízká – zkontroluj úsek, měřené poruchy a typ modelu.', 'hint_val_none': 'ověř model na jiném úseku, než na kterém byl nafitovaný (záložka Ověření).', 'hint_val_bad': 'model na ověřovacím úseku nesedí – zvaž jiný model, úsek nebo měřené poruchy.', 'hint_tune': 'nové ladění má nízkou robustnost (Ms > 2) – zvětši τc nebo zvol robustnější metodu.', 'hint_tune_bad': 'nové ladění je podle modelu nestabilní – uprav parametry.', 'hint_diag': 'diagnostika ukazuje možný problém (oscilace, stikce nebo nelinearita) – zkontroluj záložku Diagnostika.', 'hint_save': 'ulož projekt a vytvoř report (záložka Projekt a report).', 'hint_done': 'vše hotovo.'})
EN.update({'loading': 'Loading file…', 'auto_title': 'Automatically found segments ({n})', 'auto_none': 'No significant MV or SP steps were found. Select a segment manually or let the Test plan tab design a test.', 'auto_from': 'From [s]', 'auto_to': 'To [s]', 'auto_len': 'Length [min]', 'auto_steps': 'MV / SP steps', 'auto_dirs': 'Directions', 'auto_quality': 'Rating', 'auto_use_id': 'Use for identification', 'auto_use_val': 'Use for validation', 'auto_help': 'Segments are clusters of MV steps (manual) or SP steps (auto) with time to settle. Select a row and apply it.', 'auto_gap': 'Max. gap between steps [s] (0 = auto)', 'h_auto_gap': 'Steps further apart form separate segments. Automatic: 3× the typical step spacing.', 'q_title': 'Data quality for identification', 'q_level0': 'suitable', 'q_level1': 'usable with caveats', 'q_level2': 'unsuitable', 'q_steps_ok': '{n} significant MV/SP steps.', 'q_steps_one': 'Only one step – the model will be less reliable, ideally at least 2 in both directions.', 'q_steps_none': 'No significant MV or SP step – the model cannot be reliably identified from this segment.', 'q_one_dir': 'All steps go in one direction – add a step in the opposite direction (also reveals nonlinearity and backlash).', 'q_snr_ok': 'Signal-to-noise ratio {s} – good.', 'q_snr_low': 'Signal-to-noise ratio only {s} – the model will be less accurate.', 'q_snr_bad': 'Signal-to-noise ratio {s} – the response is buried in noise.', 'q_lim_warn': 'MV is at its limit {p} % of the time.', 'q_lim_bad': 'MV is at its limit {p} % of the time – the data carries no process information there.', 'q_compressed': '{p} % of consecutive PV values are identical – the archive is probably compressed.', 'q_sp_ramp': 'SP changes smoothly (ramp) – SP steps give a more accurate model.', 'q_sampling': 'The data period {h} s is coarse relative to the process dynamics.', 'q_fast_steps': 'The shortest step spacing {g} s is shorter than the settling time (~{s} s) – the process cannot settle.', 'q_short_tail': 'There is no settling time after the last step (~{s} s) – extend the segment.', 'q_short': 'The segment is too short.', 'proj_build': 'Prepare project', 'prog_data': 'Data', 'prog_model': 'Model', 'prog_val': 'Validation', 'prog_tune': 'Tuning', 'prog_diag': 'Diagnostics', 'prog_save': 'Project', 'hint_next': 'Next step', 'hint_data': 'choose a better segment (Data tab – automatically found segments) or let the app design a test.', 'hint_model_none': 'run the identification in the Model tab.', 'hint_model_stale': 'the segment or settings changed – run the identification again.', 'hint_model_low': 'the model fit is low – check the segment, measured disturbances and model type.', 'hint_val_none': 'validate the model on a different segment than it was fitted on (Validation tab).', 'hint_val_bad': 'the model does not match the validation segment – consider another model, segment or measured disturbances.', 'hint_tune': 'the new tuning has low robustness (Ms > 2) – increase τc or choose a more robust method.', 'hint_tune_bad': 'the new tuning is unstable according to the model – adjust the parameters.', 'hint_diag': 'diagnostics indicate a possible problem (oscillation, stiction or nonlinearity) – check the Diagnostics tab.', 'hint_save': 'save the project and create a report (Project & report tab).', 'hint_done': 'all done.'})


# v6: horní panel
CS.update({'tb_project': 'Projekt', 'tb_help': 'Nápověda', 'tb_settings': 'Nastavení', 'tb_choose_file': 'Nahrát soubor', 'cols_title': 'Sloupce a normování', 'cols_signals': 'Signály', 'blk_title': 'Blok PIDConL – konfigurace a současné parametry', 'blk_summary': 'PIDConL: SampleTime {s} s · DiffGain {dg} · P ve zpětné vazbě {p} · D ve zpětné vazbě {d} · současné Gain {g}, TI {ti} s, TD {td} s — mění se v záložce Ladění.'})
EN.update({'tb_project': 'Project', 'tb_help': 'Help', 'tb_settings': 'Settings', 'tb_choose_file': 'Upload file', 'cols_title': 'Columns and scaling', 'cols_signals': 'Signals', 'blk_title': 'PIDConL block – configuration and current parameters', 'blk_summary': 'PIDConL: SampleTime {s} s · DiffGain {dg} · P in feedback {p} · D in feedback {d} · current Gain {g}, TI {ti} s, TD {td} s — change in the Tuning tab.'})


# v7: kritéria optimalizace, popisy metod s doporučeným využitím
CS.update({'mdesc_SIMC': '**SIMC** (Skogestad 2003) – jednoduchá analytická pravidla z modelu, jeden ladicí parametr τc (výchozí τc = θ, menší = rychlejší). **Doporučené využití:** univerzální výchozí volba pro většinu smyček, dobrý kompromis rychlosti a robustnosti.', 'mdesc_iSIMC': '**iSIMC** (Grimholt & Skogestad 2018) – vylepšené SIMC: posun o θ/3 v Gain a TI, u PID TD = θ/3. **Doporučené využití:** samoregulační procesy s výraznějším dopravním zpožděním, kde SIMC vychází zbytečně opatrně.', 'mdesc_Lambda': '**Lambda / IMC** – požadovaná odezva uzavřené smyčky bez překmitu s časovou konstantou λ (výchozí 3θ). **Doporučené využití:** smyčky, kde je důležitější klidná a předvídatelná odezva než rychlé potlačení poruch, a koordinované ladění více navazujících smyček. Pozor u pomalých a integračních procesů – poruchy dorovnává pomalu.', 'mdesc_AMIGO': '**AMIGO** (Åström & Hägglund 2004) – pravidla odvozená optimalizací pro robustnost Ms ≈ 1,4, bez ladicího parametru. **Doporučené využití:** bezpečné první nastavení, zejména když si modelem nejsi jistý nebo se proces v čase mění.', 'mdesc_OPT': '**Optimalizace** – numerické hledání parametrů přímo na identifikovaném modelu (včetně SampleTime, DiffGain a P/D ve zpětné vazbě) podle zvoleného kritéria, vždy s podmínkou robustnosti Ms. **Doporučené využití:** když chceš z modelu vytěžit maximum a model je ověřený.', 'mdesc_AVG': '**Průměrovací ladění** (Skogestad) – regulátor co nejpomalejší, ale hladina nepřekročí povolenou odchylku. **Doporučené využití:** vyrovnávací nádrže, kde má být klidný odtok a hladina může kolísat.', 'opt_crit': 'Kritérium', 'h_opt_crit': 'Co se má minimalizovat. Podmínka robustnosti Ms platí pro všechna kritéria.', 'crit_MIGO': 'MIGO', 'crit_IAE': 'IAE', 'crit_ISE': 'ISE', 'crit_ITAE': 'ITAE', 'crit_OVS': 'IAE + limit překmitu', 'cdesc_MIGO': '**MIGO** – maximalizuje integrační zesílení Gain/TI, tedy minimalizuje integrál odchylky při poruše, za podmínky Ms. **Využití:** nejlepší potlačení poruch při zaručené robustnosti; výchozí volba.', 'cdesc_IAE': '**IAE** (∫|e| dt, „Error Min.“) – součet absolutních odchylek. **Využití:** vyvážený kompromis rychlosti a tlumení; nejčastější obecné kritérium.', 'cdesc_ISE': '**ISE** (∫e² dt, „Nonlinear Min.“) – velké odchylky trestá výrazně víc než malé. **Využití:** když vadí hlavně velké výkyvy (hladina blízko limitu, bezpečnostní meze); vede k razantnější regulaci a větším pohybům MV.', 'cdesc_ITAE': '**ITAE** (∫t·|e| dt, „Time Weighted“) – trestá odchylky, které trvají dlouho. **Využití:** krátká doba ustálení a málo dokmitávání, obvykle o něco klidnější než IAE; oblíbené pro odezvu na SP.', 'cdesc_OVS': '**IAE s limitem překmitu** („Overshoot Min.“) – IAE, ale překmit nad zvolený limit je penalizovaný. **Využití:** procesy, kde PV nesmí přestřelit SP (teplota, tlak, dávkování); o něco pomalejší než čisté IAE. U integračních procesů je překmit při změně SP s P složkou na odchylku nevyhnutelný – použij P ve zpětné vazbě.', 'opt_target': 'Ladit na', 'h_opt_target': 'Na jakou odezvu se kritérium počítá: skok poruchy na vstupu procesu, skok SP, nebo průměr obou (každá normovaná).', 'tgt_dist': 'poruchu', 'tgt_sp': 'změnu SP', 'tgt_both': 'obojí', 'opt_ovs': 'Max. překmit', 'h_opt_ovs': 'Povolený překmit odezvy (u poruchy překmit na opačnou stranu).', 'note_topt': 'Optimalizováno podle zvoleného kritéria při Ms ≤ {ms}. Limity MV a deadband se neuvažují (malé skoky) – ověř je v simulaci níže.', 'note_ovs_fail': 'Limit překmitu {lim:.0f} % nešel při dané robustnosti splnit (dosaženo {r:.0f} %). U integračních procesů zapni P ve zpětné vazbě, případně povol větší překmit.', 'ovs_col': 'Překmit SP [%]', 'use_col': 'Doporučené využití', 'use_SIMC': 'univerzální výchozí volba', 'use_iSIMC': 'samoregulační procesy s větším zpožděním', 'use_Lambda': 'klidná odezva, navazující smyčky', 'use_AMIGO': 'bezpečné první nastavení, nejistý model', 'use_AVG': 'vyrovnávací nádrže, klidný odtok', 'use_MIGO': 'nejlepší potlačení poruch s robustností', 'use_IAE': 'vyvážená rychlost a tlumení', 'use_ISE': 'potlačení velkých výkyvů', 'use_ITAE': 'rychlé ustálení, málo dokmitávání', 'use_OVS': 'odezva bez překmitu', 'cmp_help': 'IAE poruchy = odezva na skok 1 % na vstupu procesu, IAE SP = skok SP o 1 % (menší = lepší), překmit při změně SP. Porovnávej při podobném Ms. Kliknutím na řádek metodu použiješ.'})
EN.update({'mdesc_SIMC': '**SIMC** (Skogestad 2003) – simple analytical rules from the model, one tuning parameter τc (default τc = θ, smaller = faster). **Recommended use:** universal default for most loops, a good compromise between speed and robustness.', 'mdesc_iSIMC': '**iSIMC** (Grimholt & Skogestad 2018) – improved SIMC: θ/3 shift in Gain and TI, PID with TD = θ/3. **Recommended use:** self-regulating processes with larger dead time, where SIMC is unnecessarily cautious.', 'mdesc_Lambda': '**Lambda / IMC** – desired closed-loop response without overshoot with time constant λ (default 3θ). **Recommended use:** loops where a smooth, predictable response matters more than fast disturbance rejection, and coordinated tuning of interacting loops. Beware with slow and integrating processes – disturbances are corrected slowly.', 'mdesc_AMIGO': '**AMIGO** (Åström & Hägglund 2004) – rules derived by optimization for robustness Ms ≈ 1.4, no tuning parameter. **Recommended use:** a safe first setting, especially when the model is uncertain or the process changes over time.', 'mdesc_OPT': '**Optimization** – numerical search for parameters directly on the identified model (incl. SampleTime, DiffGain and P/D in feedback) by the chosen criterion, always with the robustness constraint Ms. **Recommended use:** when you want the most out of a validated model.', 'mdesc_AVG': '**Averaging tuning** (Skogestad) – the slowest controller that keeps the level within the allowed deviation. **Recommended use:** surge tanks where the outflow should be smooth and the level may vary.', 'opt_crit': 'Criterion', 'h_opt_crit': 'What to minimize. The robustness constraint Ms applies to all criteria.', 'crit_MIGO': 'MIGO', 'crit_IAE': 'IAE', 'crit_ISE': 'ISE', 'crit_ITAE': 'ITAE', 'crit_OVS': 'IAE + overshoot limit', 'cdesc_MIGO': '**MIGO** – maximizes the integral gain Gain/TI, i.e. minimizes the integrated error after a disturbance, subject to Ms. **Use:** best disturbance rejection with guaranteed robustness; default.', 'cdesc_IAE': '**IAE** (∫|e| dt, “Error Min.”) – sum of absolute errors. **Use:** a balanced compromise between speed and damping; the most common general criterion.', 'cdesc_ISE': '**ISE** (∫e² dt, “Nonlinear Min.”) – penalizes large errors much more than small ones. **Use:** when mainly large deviations matter (level near a limit, safety bounds); gives more aggressive control and larger MV moves.', 'cdesc_ITAE': '**ITAE** (∫t·|e| dt, “Time Weighted”) – penalizes long-lasting errors. **Use:** short settling time and little lingering oscillation, usually slightly smoother than IAE; popular for SP response.', 'cdesc_OVS': '**IAE with overshoot limit** (“Overshoot Min.”) – IAE with overshoot above the chosen limit penalized. **Use:** processes where PV must not overshoot SP (temperature, pressure, dosing); slightly slower than plain IAE. For integrating processes SP overshoot is unavoidable with P on error – use P in feedback.', 'opt_target': 'Tune for', 'h_opt_target': 'Which response the criterion is evaluated on: a disturbance step at the process input, an SP step, or the average of both (each normalized).', 'tgt_dist': 'disturbance', 'tgt_sp': 'SP change', 'tgt_both': 'both', 'opt_ovs': 'Max. overshoot', 'h_opt_ovs': 'Allowed overshoot (for disturbances, overshoot to the opposite side).', 'note_topt': 'Optimized by the chosen criterion with Ms ≤ {ms}. MV limits and deadband are not considered (small steps) – check them in the simulation below.', 'note_ovs_fail': 'The {lim:.0f} % overshoot limit could not be met at this robustness (achieved {r:.0f} %). For integrating processes enable P in feedback or allow a larger overshoot.', 'ovs_col': 'SP overshoot [%]', 'use_col': 'Recommended use', 'use_SIMC': 'universal default', 'use_iSIMC': 'self-regulating processes with larger delay', 'use_Lambda': 'smooth response, interacting loops', 'use_AMIGO': 'safe first setting, uncertain model', 'use_AVG': 'surge tanks, smooth outflow', 'use_MIGO': 'best disturbance rejection with robustness', 'use_IAE': 'balanced speed and damping', 'use_ISE': 'suppressing large deviations', 'use_ITAE': 'fast settling, little oscillation', 'use_OVS': 'response without overshoot', 'cmp_help': 'IAE disturbance = response to a 1 % step at the process input, IAE SP = 1 % SP step (lower = better), overshoot on SP change. Compare at similar Ms. Click a row to use that method.'})


# v8: neměřené poruchy, fixace, hodnocení, prvky smyčky, scénáře, stikce
CS.update({'dist_level': 'Neměřené poruchy', 'dl_none': 'žádné', 'dl_medium': 'střední', 'dl_high': 'silné', 'h_dist_level': 'Jak potlačit vliv poruch, které nejsou v datech měřené (drift, změny složení, počasí…). Vyzkoušej všechny úrovně a porovnej hodnocení modelu.', 'dist_strength': 'Síla potlačení', 'h_dist_strength': 'Vyšší = potlačí i rychlejší poruchy (časové měřítko se zkrátí). Příliš vysoká může odstranit i užitečnou odezvu procesu.', 'dl_desc_none': 'Neměřené poruchy se nepotlačují – vhodné pro čistá data (skokový test bez rušení).', 'dl_desc_medium': '**Střední:** data se před fitem profiltrují horní propustí – odstraní se pomalé změny (drift), odezvy na skoky MV zůstanou. Vhodné pro samoregulační procesy s pomalým rušením.', 'dl_desc_high': '**Silné:** pomalá neměřená porucha se odhaduje společně s modelem (vyhlazená křivka). Nejsilnější potlačení; u integračních procesů (hladina) je oddělení poruchy od vlivu MV principiálně obtížné – pokud můžeš, přidej měřenou poruchu (např. přítok).', 'gain_sign': 'Znaménko zesílení', 'gs_auto': 'auto', 'gs_pos': '+', 'gs_neg': '−', 'h_gain_sign': 'Když víš, jestli PV při zvýšení MV roste (+) nebo klesá (−), vynucení znaménka zabrání nesmyslným modelům u rušených dat.', 'id_stic': 'Identifikovat stikci', 'h_id_stic': 'Současně s modelem odhadne stikci ventilu (výstup regulátoru → skutečná poloha). Vhodné pro data z automatu; výpočet je několikrát delší.', 'refit_done': 'Dofitováno ({n} zafixovaných parametrů).', 'col_status': 'Hodnocení', 'st_0': 'výborný', 'st_1': 'velmi dobrý', 'st_2': 'dobrý', 'st_3': 'slabý', 'st_4': 'špatný', 'col_stic': 'Stikce [{u}]', 'col_rawfit': 'FIT surová data [%]', 'fit_eff_note': 'Při potlačení neměřených poruch se FIT počítá na datech po potlačení; FIT na surových datech je ve vlastním sloupci.', 'fix_help': 'Zaškrtni „fix“ u parametrů, které znáš (např. θ), uprav jejich hodnotu a klikni na Dofitovat – dopočítají se jen ostatní.', 'fix': 'fix', 'h_fix': 'Zafixovat hodnotu při dofitování.', 'stic_param': 'Stikce S [{u}]', 'h_stic_param': 'Pásmo, o které se musí výstup regulátoru změnit, než se ventil pohne.', 'refit': 'Dofitovat', 'h_refit': 'Nový fit tohoto modelu se zafixovanými parametry (ostatní se dopočítají).', 'model_wo_dist': 'model bez poruchy', 'dl_view': 'Neměřené poruchy – co udělalo potlačení (měřítko {th} s)', 'dl_est': 'odhad neměřené poruchy', 'dl_filtered_pv': 'PV po filtraci', 'dl_filtered_model': 'model po filtraci', 'dl_view_help_medium': 'Data i model po horní propusti – fit porovnává jen rychlejší změny, pomalý drift je odstraněný.', 'dl_view_help_high': 'Odhadnutý průběh neměřené poruchy, který se k modelu přičítá. Pokud kopíruje i odezvy na skoky MV, je potlačení příliš silné – sniž sílu.', 'eval_title': 'Hodnocení modelu', 'eval_id': 'Úsek identifikace', 'eval_val': 'Ověřovací úsek', 'eval_iae': 'IAE [{u}]', 'eval_white': 'Rezidua – autokorelace mimo mez', 'eval_ccf': 'Rezidua × ΔMV mimo mez', 'eval_st_0': '**Výborný model** – vysoká shoda a rezidua bez vlivu MV.', 'eval_st_1': '**Velmi dobrý model** – vhodný pro ladění.', 'eval_st_2': '**Dobrý model** – pro ladění použitelný, výsledky ověř simulací.', 'eval_st_3': '**Slabý model** – laď opatrně (robustně), zvaž jiný úsek, typ modelu nebo měřené poruchy.', 'eval_st_4': '**Špatný model** – pro ladění nevhodný.', 'eval_ccf_bad': 'Rezidua korelují se změnami MV – model nevysvětluje celý vliv MV (zkus jiný řád, zpoždění nebo zafixuj známé parametry).', 'eval_acf_bad': 'Rezidua jsou výrazně autokorelovaná – zbylo v nich rušení nebo nevysvětlená pomalá dynamika. U provozních dat běžné; pokud korelace s MV je v pořádku, model je použitelný. Zkus potlačení neměřených poruch.', 'eval_res_ok': 'Rezidua vypadají jako šum – model zachytil dynamiku dobře.', 'eval_no_val': 'Tip: v záložce Ověření vyber jiný úsek – hodnocení se tu zobrazí i pro něj.', 'eval_acf_t': 'Autokorelace reziduí', 'eval_ccf_t': 'Korelace reziduí s ΔMV', 'eval_help': 'FIT = 100·(1 − ‖e‖/‖PV − průměr‖), NRMSE = RMS chyby / rozsah PV, IAE = průměrná absolutní chyba. Sloupce mimo tečkované meze (99 %) jsou červeně. Korelace reziduí s ΔMV je důležitější než jejich autokorelace.', 'blk_elems': 'Prvky smyčky', 'h_blk_elems': 'Filtr PV, omezení rychlosti MV a rampa SP – v PCS 7 buď parametry bloku, nebo samostatné bloky v CFC. Zahrnou se do simulace, robustnosti i optimalizace.', 'pvfilt': 'Filtr PV [s]', 'h_pvfilt': 'Časová konstanta filtru měření PV (0 = bez filtru). Filtr přidává do smyčky zpoždění – zhoršuje robustnost.', 'mvrate': 'Max. rychlost MV [{u}/s]', 'h_mvrate': 'Omezení rychlosti změny výstupu (0 = bez omezení). Optimalizace ho respektuje jako podmínku.', 'sprate': 'Rampa SP [{u}/s]', 'h_sprate': 'Omezení rychlosti změny žádané hodnoty (0 = skokem).', 'note_scen_missing': 'Scénář ještě není sestavený – optimalizováno na skoky (obojí). Po zobrazení simulace se výpočet zopakuje na scénáři.', 'note_scen': 'Optimalizováno na scénáři simulace (včetně limitů, rychlosti MV, stikce a charakteristiky ventilu) při Ms ≤ {ms}.', 'tgt_scen': 'scénář simulace', 'scen_custom': 'Vlastní scénář', 'scen_title': 'Scénář – události', 'sc_on': 'Zap.', 'sc_target': 'Kam působí', 'sc_type': 'Typ', 'sc_amp': 'Amplituda', 'sc_start': 'Začátek [s]', 'sc_end': 'Konec [s]', 'sc_period': 'Perioda / délka [s]', 'sc_tau': 'Setrvačnost [s]', 'h_sc_target': 'SP = změna žádané hodnoty; Vstup procesu = neměřená porucha na vstupu (jako změna MV); PV = porucha přičtená k PV; Měřená porucha = působí přes identifikovaný model poruchy (a FF).', 'h_sc_type': 'Skok, rampa (od začátku do konce), sinus, pravidelné pulzy, náhodné pulzy, šum.', 'h_sc_amp': 'V jednotkách cíle: SP a PV v jednotkách PV, vstup procesu v jednotkách MV, měřená porucha ve svých jednotkách. U šumu směrodatná odchylka.', 'h_sc_end': 'Prázdné = do konce simulace.', 'h_sc_period': 'Perioda sinusu a pulzů, u náhodných pulzů střední odstup; u rampy délka, pokud není konec.', 'h_sc_tau': 'Volitelná setrvačnost (filtr 1. řádu) signálu – např. pomalé působení poruchy na PV.', 'tg_SP': 'SP', 'tg_IN': 'Vstup procesu', 'tg_PV': 'PV (výstup)', 'tg_M': 'Měřená', 'ty_step': 'skok', 'ty_ramp': 'rampa', 'ty_sine': 'sinus', 'ty_pulse': 'pulzy', 'ty_rpulse': 'náhodné pulzy', 'ty_noise': 'šum', 'scen_help': 'Řádky můžeš přidávat, mazat i vypínat. Scénář se použije pro simulaci i pro optimalizaci s cílem „scénář simulace“.', 'plant_title': 'Proces a ventil v simulaci', 'plant_help': 'Vlastnosti skutečného zařízení, které lineární model neobsahuje. Použijí se v simulaci, při ověření na záznamu a při optimalizaci na scénáři.', 'sim_stic': 'Stikce S [{u}]', 'h_sim_stic': 'Předvyplněno identifikovanou stikcí modelu. 0 = ventil bez stikce.', 'sim_slip': 'Skok ventilu J [% S]', 'h_sim_slip': '100 % = typická stikce (ventil skočí až na výstup regulátoru), 0 % = čistá vůle.', 'sim_noise': 'Šum PV σ [{u}]', 'h_sim_noise': 'Šum měření v simulaci. Odhad z reziduí modelu: {s}.', 'vchar_title': 'Charakteristika ventilu', 'h_vchar': 'Relativní zesílení v každém pásmu polohy ventilu (1 = lineární). Např. 0,5 / 0,25 / 0,1 nad 70 % simuluje saturaci průtoku u otevřeného ventilu.', 'vchar_band': 'Pásmo [{u}]', 'vchar_gain': 'Zesílení', 'vchar_x': 'poloha ventilu [%]', 'vchar_y': 'efektivní MV [%]', 'valve_pos': 'poloha ventilu', 'kpi_rev': 'Pohyby ventilu (změny směru)', 'h_opt_target': 'Na jakou odezvu se kritérium počítá: skok poruchy na vstupu procesu, skok SP, průměr obou, nebo celý scénář simulace včetně nelineárních prvků (pomalejší).', 'h_scenario': 'Vlastní scénář = tabulka událostí (skoky, rampy, sinus, pulzy, šum). Naměřené poruchy = přehraje skutečné průběhy z úseku.'})
EN.update({'dist_level': 'Unmeasured disturbances', 'dl_none': 'none', 'dl_medium': 'medium', 'dl_high': 'high', 'h_dist_level': 'How to suppress disturbances not measured in the data (drift, composition, weather…). Try all levels and compare the model evaluation.', 'dist_strength': 'Suppression strength', 'h_dist_strength': 'Higher = also suppresses faster disturbances (shorter time scale). Too high may remove useful process response.', 'dl_desc_none': 'Unmeasured disturbances are not suppressed – suitable for clean data (undisturbed step test).', 'dl_desc_medium': '**Medium:** the data are high-pass filtered before fitting – slow changes (drift) are removed, responses to MV steps remain. Suitable for self-regulating processes with slow disturbances.', 'dl_desc_high': '**High:** the slow unmeasured disturbance is estimated together with the model (smoothed curve). Strongest suppression; for integrating processes (level) separating disturbance from MV effect is inherently hard – add a measured disturbance (e.g. inflow) if you can.', 'gain_sign': 'Gain sign', 'gs_auto': 'auto', 'gs_pos': '+', 'gs_neg': '−', 'h_gain_sign': 'If you know whether PV rises (+) or falls (−) when MV increases, forcing the sign prevents meaningless models on disturbed data.', 'id_stic': 'Identify stiction', 'h_id_stic': 'Estimates valve stiction (controller output → actual position) together with the model. Suitable for auto-mode data; takes several times longer.', 'refit_done': 'Refitted ({n} fixed parameters).', 'col_status': 'Rating', 'st_0': 'excellent', 'st_1': 'very good', 'st_2': 'good', 'st_3': 'fair', 'st_4': 'poor', 'col_stic': 'Stiction [{u}]', 'col_rawfit': 'FIT raw data [%]', 'fit_eff_note': 'With disturbance suppression the FIT is computed on the suppressed data; FIT on raw data is in its own column.', 'fix_help': 'Tick “fix” for parameters you know (e.g. θ), adjust the value and click Refit – only the others are estimated.', 'fix': 'fix', 'h_fix': 'Keep this value fixed when refitting.', 'stic_param': 'Stiction S [{u}]', 'h_stic_param': 'Band the controller output must move before the valve moves.', 'refit': 'Refit', 'h_refit': 'New fit of this model with the fixed parameters (others are estimated).', 'model_wo_dist': 'model without disturbance', 'dl_view': 'Unmeasured disturbances – effect of suppression (scale {th} s)', 'dl_est': 'estimated unmeasured disturbance', 'dl_filtered_pv': 'filtered PV', 'dl_filtered_model': 'filtered model', 'dl_view_help_medium': 'Data and model after the high-pass filter – the fit compares only faster changes, slow drift is removed.', 'dl_view_help_high': 'Estimated unmeasured disturbance added to the model. If it also follows the responses to MV steps, the suppression is too strong – reduce the strength.', 'eval_title': 'Model evaluation', 'eval_id': 'Identification segment', 'eval_val': 'Validation segment', 'eval_iae': 'IAE [{u}]', 'eval_white': 'Residuals – autocorrelation out of bounds', 'eval_ccf': 'Residuals × ΔMV out of bounds', 'eval_st_0': '**Excellent model** – high fit and residuals free of MV influence.', 'eval_st_1': '**Very good model** – suitable for tuning.', 'eval_st_2': '**Good model** – usable for tuning, verify results by simulation.', 'eval_st_3': '**Fair model** – tune cautiously (robustly), consider another segment, model type or measured disturbances.', 'eval_st_4': '**Poor model** – not suitable for tuning.', 'eval_ccf_bad': 'Residuals correlate with MV changes – the model does not explain the whole MV effect (try another order, dead time or fix known parameters).', 'eval_acf_bad': 'Residuals are strongly autocorrelated – disturbances or unexplained slow dynamics remain. Common with plant data; if the MV correlation is fine, the model is usable. Try disturbance suppression.', 'eval_res_ok': 'Residuals look like noise – the model captured the dynamics well.', 'eval_no_val': 'Tip: select a different segment in the Validation tab – its evaluation will appear here too.', 'eval_acf_t': 'Residual autocorrelation', 'eval_ccf_t': 'Residual correlation with ΔMV', 'eval_help': 'FIT = 100·(1 − ‖e‖/‖PV − mean‖), NRMSE = RMS error / PV range, IAE = mean absolute error. Bars outside the dotted 99 % bounds are red. Correlation of residuals with ΔMV matters more than autocorrelation.', 'blk_elems': 'Loop elements', 'h_blk_elems': 'PV filter, MV rate limit and SP ramp – in PCS 7 either block parameters or separate CFC blocks. Included in simulation, robustness and optimization.', 'pvfilt': 'PV filter [s]', 'h_pvfilt': 'Time constant of the PV measurement filter (0 = none). The filter adds lag to the loop and reduces robustness.', 'mvrate': 'Max. MV rate [{u}/s]', 'h_mvrate': 'Limit on the output rate of change (0 = none). Optimization respects it as a constraint.', 'sprate': 'SP ramp [{u}/s]', 'h_sprate': 'Limit on the setpoint rate of change (0 = step).', 'note_scen_missing': 'The scenario is not built yet – optimized on steps (both). The computation is repeated on the scenario once the simulation is shown.', 'note_scen': 'Optimized on the simulation scenario (incl. limits, MV rate, stiction and valve characteristic) with Ms ≤ {ms}.', 'tgt_scen': 'simulation scenario', 'scen_custom': 'Custom scenario', 'scen_title': 'Scenario – events', 'sc_on': 'On', 'sc_target': 'Acts on', 'sc_type': 'Type', 'sc_amp': 'Amplitude', 'sc_start': 'Start [s]', 'sc_end': 'End [s]', 'sc_period': 'Period / length [s]', 'sc_tau': 'Lag [s]', 'h_sc_target': 'SP = setpoint change; Process input = unmeasured disturbance at the input (like an MV change); PV = disturbance added to PV; Measured disturbance = acts through the identified disturbance model (and FF).', 'h_sc_type': 'Step, ramp (from start to end), sine, regular pulses, random pulses, noise.', 'h_sc_amp': 'In units of the target: SP and PV in PV units, process input in MV units, measured disturbance in its own units. For noise the standard deviation.', 'h_sc_end': 'Empty = until the end of the simulation.', 'h_sc_period': 'Period of sine and pulses, mean spacing of random pulses; ramp length if no end is given.', 'h_sc_tau': 'Optional lag (first-order filter) of the signal – e.g. slow effect of a disturbance on PV.', 'tg_SP': 'SP', 'tg_IN': 'Process input', 'tg_PV': 'PV (output)', 'tg_M': 'Measured', 'ty_step': 'step', 'ty_ramp': 'ramp', 'ty_sine': 'sine', 'ty_pulse': 'pulses', 'ty_rpulse': 'random pulses', 'ty_noise': 'noise', 'scen_help': 'Rows can be added, deleted and switched off. The scenario is used for simulation and for optimization with target “simulation scenario”.', 'plant_title': 'Process and valve in simulation', 'plant_help': 'Properties of the real plant not contained in the linear model. Used in simulation, in validation on recorded data and in scenario optimization.', 'sim_stic': 'Stiction S [{u}]', 'h_sim_stic': 'Prefilled with the identified stiction of the model. 0 = no stiction.', 'sim_slip': 'Valve slip J [% S]', 'h_sim_slip': '100 % = typical stiction (valve jumps to the controller output), 0 % = pure backlash.', 'sim_noise': 'PV noise σ [{u}]', 'h_sim_noise': 'Measurement noise in the simulation. Estimate from model residuals: {s}.', 'vchar_title': 'Valve characteristic', 'h_vchar': 'Relative gain in each valve position band (1 = linear). E.g. 0.5 / 0.25 / 0.1 above 70 % simulates flow saturation of a wide-open valve.', 'vchar_band': 'Band [{u}]', 'vchar_gain': 'Gain', 'vchar_x': 'valve position [%]', 'vchar_y': 'effective MV [%]', 'valve_pos': 'valve position', 'kpi_rev': 'Valve moves (reversals)', 'h_opt_target': 'Which response the criterion is evaluated on: disturbance step at the process input, SP step, the average of both, or the whole simulation scenario incl. nonlinear elements (slower).', 'h_scenario': 'Custom scenario = table of events (steps, ramps, sine, pulses, noise). Measured disturbances = replays real signals from the segment.'})
