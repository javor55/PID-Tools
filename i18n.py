"""Texty aplikace / application texts (cs, en)."""

TEXTS = {
    "cs": {
        # obecné
        "title": "Identifikace procesu a ladění PIDConL",
        "empty": "Nahraj vlevo export z PCS 7 nebo Process Historianu (CSV/Excel), případně si vyzkoušej ukázková data.",
        "status": "{n} vzorků · perioda dat {ts} s · délka {dur} s · PV {pvr} · MV {mvr}",
        "status_model": "model připraven",
        "status_nomodel": "model zatím není nafitovaný",
        "tab1": "1 · Data", "tab2": "2 · Model", "tab3": "3 · Ladění PIDConL", "tab4": "4 · Ověření",
        "time_s": "čas [s]", "dists": "poruchy", "fit": "fit", "edited": "upravený", "prediction": "predikce",
        "measured": "naměřená", "simulated": "simulace", "current": "Současné", "new": "Nové",
        "new_err": "Nové – chyba modelu", "setting": "Nastavení", "resid": "Reziduum",

        # postranní panel
        "sb_data": "Data", "source": "Zdroj", "src_file": "Soubor", "src_demo": "Ukázka",
        "upload": "CSV nebo Excel z PCS 7 / Process Historianu",
        "demo_desc": "Simulovaná nádrž: hladina (integrační proces), MV = odtokový ventil, měřený přítok jako "
                     "porucha. Ruční režim se skoky MV.",
        "demo_dl": "Stáhnout ukázková data",
        "long_fmt": "Dlouhý formát (tag, čas, hodnota)",
        "long_fmt_help": "Typický export z historianu – řádek = tag, čas, hodnota. Aplikace ho přeskládá do sloupců.",
        "sb_columns": "Sloupce", "time_unit": "Jednotka číselného času",
        "time_unit_help": "Použije se, jen když je čas číslo, ne datum.",
        "col_tag": "Sloupec s názvem tagu", "col_time": "Čas", "col_value": "Sloupec s hodnotou",
        "col_sp": "SP (nepovinné)", "col_dist": "Měřené poruchy (nepovinné)",
        "col_dist_help": "Např. přítok do nádrže. Zlepší identifikaci a umožní návrh dopředné vazby.",
        "ts_manual": "Zadat periodu dat ručně", "ts_data": "Perioda dat [s]",
        "sb_norm": "Normování (NormPV, NormMV)",
        "unit_pv": "Jednotka PV", "unit_mv": "Jednotka MV",
        "norm_help": "Zadej stejné rozsahy jako v bloku – Gain pak odpovídá přímo hodnotě ve faceplatu.",
        "sb_block": "Konfigurace bloku", "sampletime": "SampleTime (cyklus OB) [s]",
        "sampletime_help": "Např. OB32 = 1 s, OB35 = 0,1 s – podle OB, ve kterém blok běží.",
        "diffgain_help": "Poměr TD / časová konstanta filtru D složky.",
        "pfb": "P složka ve zpětné vazbě (jen PV)",
        "pfb_help": "Skok SP pak nevyvolá skok MV – klidnější odezva na SP, potlačení poruch beze změny.",
        "dfb": "D složka ve zpětné vazbě (jen PV)",
        "deadband": "Deadband [j. PV]", "db_mode": "Deadband", "db_cont": "spojitý", "db_step": "skokový",
        "db_mode_help": "Spojitý: odchylka se zmenší o šířku pásma. Skokový: uvnitř pásma nula, mimo plná odchylka. "
                        "Ověř, jak ho zpracovává tvoje verze APL.",
        "sb_current": "Současné parametry (faceplate)", "ti_zero": "TI [s] (0 = bez I)",
        "sb_display": "Zobrazení", "plot_height": "Výška grafů [px]",

        # data
        "seg_intro": "Vyber úsek pro identifikaci: výrazné změny MV (skoky v ručním režimu nebo skoky SP v automatu), "
                     "bez neměřených poruch a bez MV v limitu.",
        "seg_id": "Úsek pro identifikaci [s]", "mouse": "Myš v grafu",
        "mouse_zoom": "Přiblížit", "mouse_select": "Vybrat úsek",
        "seg_tip": "Tip: v režimu „Vybrat úsek“ táhni myší přes graf a úsek se nastaví sám. Dvojklik vrátí přiblížení. "
                   "Kliknutím na položku legendy křivku skryješ, dvojklikem zobrazíš jen ji.",
        "info_auto": "V úseku se mění SP – data jsou z automatu. Pro identifikaci jsou vhodná, pokud obsahují výrazné skoky SP.",
        "warn_limit": "MV je v {pct} % úseku v limitu – tam smyčka nepracuje a data nenesou informaci o procesu.",
        "warn_irregular": "{name}: časové značky jsou nerovnoměrné – archiv je pravděpodobně komprimovaný. Průběh mezi "
                          "body je dopočtený a může zkreslit hlavně dopravní zpoždění.",
        "warn_repeated": "{name}: víc než polovina po sobě jdoucích hodnot je stejná – data jsou nejspíš komprimovaná nebo "
                         "zaokrouhlená. Zvaž export bez komprese.",

        # model
        "models": "Modely", "thmax": "Max. θ [s]",
        "thmax_help": "Horní mez dopravního zpoždění. Fit zkouší θ od 0 do této hodnoty – rozumná mez (2–3× očekávané "
                      "zpoždění) zpřesní a zrychlí hledání.",
        "run_fit": "Identifikovat", "fitting": "Fituji",
        "info_fit": "Vyber modely a spusť identifikaci.",
        "warn_stale": "Data, úsek nebo nastavení se od posledního fitu změnily – spusť identifikaci znovu.",
        "warn_dists_changed": "Výběr měřených poruch se od posledního fitu změnil – spusť identifikaci znovu.",
        "col_model": "Model", "col_fit": "Shoda",
        "units_note": "Veličiny v % normovacích rozsahů: K v %/%, Ki v %/(%·s), Kd v % PV na jednotku poruchy "
                      "(u integračních za sekundu). T1, T2, Tp, θ v sekundách. U integračních modelů se fituje i "
                      "počáteční drift.",
        "warn_long_T": "{m}: T1 je delší než celý úsek dat – proces se v tomto rozsahu chová prakticky jako integrační.",
        "warn_theta_max": "{m}: θ je na horní mezi – zvyš limit nebo zkontroluj data.",
        "edit_title": "Model pro ladění", "model_for_tuning": "Model",
        "dist_model": "Model poruchy",
        "help_gain": "Zesílení procesu (u integračních rychlost náběhu).",
        "help_T": "Časová konstanta [s].", "help_theta": "Dopravní zpoždění [s].",
        "reset_fit": "Obnovit z fitu", "fit_fit": "Shoda – fit", "fit_edit": "Shoda – upravený",
        "step_title": "Odezva modelu na skok MV o 10 %",
        "show_resid": "Zobrazit rezidua (PV − model)",
        "compare_all": "Porovnat všechny modely",
        "model_P0D": "0. řád (zesílení + zpoždění)", "model_P1D": "1. řád + zpoždění (FOPDT)",
        "model_P2D": "2. řád + zpoždění (SOPDT)", "model_I0D": "Integrační + zpoždění",
        "model_I1D": "Integrační + 1. řád + zpoždění",

        # ladění
        "need_model": "Nejdřív nafituj model v záložce 2 · Model.",
        "samp_note": "SampleTime {s} s (k θ přičteno {h} s)",
        "method": "Metoda", "m_SIMC": "SIMC", "m_Lambda": "Lambda", "m_AVG": "Průměrovací",
        "method_help": "Popis zvolené metody je pod přepínačem. Porovnání všech metod najdeš níže.",
        "ctrl_type": "Regulátor",
        "avg_dpv": "Max. povolená odchylka hladiny [{u}]",
        "avg_dmv": "Změna MV při největší poruše [{u}]",
        "avg_dmv_help": "O kolik musí MV změnit, aby vyrovnal největší očekávanou poruchu.",
        "tc": "Cílová časová konstanta smyčky τc / λ [s]",
        "tc_help": "Menší hodnota = rychlejší a agresivnější regulace, větší = klidnější a robustnější.",
        "params_title": "Parametry pro PIDConL",
        "params_help": "Předvyplněno návrhem, lze ručně doladit. Ideální tvar: MV = Gain·[ER + (1/TI)∫ER dt + TD·dER/dt], "
                       "zpoždění D = TD/DiffGain.",
        "warn_neg_gain": "Gain vychází záporný – proces má záporné zesílení (např. hladina × odtokový ventil). V bloku "
                         "nastav opačný smysl působení podle konfigurace APL (záporný Gain nebo invertování).",
        "warn_low_fit": "Shoda modelu je nízká – parametry ber orientačně.",
        "ff_title": "Dopředná vazba (feedforward)", "ff_use": "Použít pro {d}",
        "ff_gain": "Zesílení FF [% MV na 1 j. {d}]",
        "ff_faster": "{d}: porucha působí rychleji (θd = {td} s) než MV (θ = {t} s) – statická FF ji úplně "
                     "nevykompenzuje, ale výrazně zmenší.",
        "ff_help": "Zašuměné měření poruchy se přes FF přenáší přímo do MV – zvaž filtr. Hodnota je v % rozsahu MV na "
                   "jednotku poruchy; před zapojením do vstupu dopředné vazby přepočítej podle normování v CFC.",
        "compare_title": "Porovnání a simulace",
        "ms": "Ms (cíl 1,4–1,8)", "gm": "Amplitudová bezpečnost (cíl > 2)", "pm": "Fázová bezpečnost [°] (cíl > 45)",
        "robust_help": "Ms = maximum citlivostní funkce: čím menší, tím robustnější smyčka. Nad 2 bývá smyčka "
                       "náchylná na kmitání při změně procesu.",
        "err_unstable": "{n}: smyčka je podle modelu nestabilní.",
        "scenario": "Scénář", "scen_steps": "Skoky SP a poruch", "scen_replay": "Naměřené poruchy",
        "sim_len": "Délka [s]", "sp_step": "Skok SP [{u}]", "dmv_step": "Neměřená porucha [{u}]",
        "dmv_step_help": "Skok přičtený ke vstupu procesu ve 40 % simulace.",
        "d_step": "Skok {d}",
        "replay_help": "Přehraje skutečný průběh měřených poruch z úseku identifikace při konstantním SP.",
        "robust_on": "Citlivost na chybu modelu (K ×1,3, θ ×1,5)",
        "err_sim_unstable": "{n}: simulace je nestabilní.",
        "kpi_maxdev": "Max. odchylka PV [{u}]", "kpi_mvrange": "Rozsah MV [{u}]",
        "kpi_mvtravel": "Pohyb MV celkem [{u}]",
        "kpi_help": "Pohyb MV celkem = součet všech změn výstupu, měřítko namáhání ventilu. Max. odchylka zahrnuje i "
                    "změny SP.",
        "download": "Stáhnout výsledek (CSV)",

        # ověření
        "val_intro": "Ověř model na jiném úseku, než na kterém byl nafitovaný. Když sedí i tam, je důvěryhodný.",
        "seg_val": "Ověřovací úsek [s]", "val_mode": "Způsob",
        "val_pred": "Predikce z MV", "val_cl": "Simulace smyčky",
        "val_mode_help": "Predikce: model dostane naměřenou MV a předpovídá PV – pro jakákoli data. Simulace smyčky: "
                         "model + PIDConL dostanou naměřené SP – pro úseky v automatu.",
        "fit_pred": "Shoda predikce PV", "need_sp": "Pro simulaci smyčky je potřeba sloupec SP.",
        "val_params": "Parametry", "val_cur": "Současné (jak smyčka běžela)", "val_new": "Nové (co by se stalo)",
        "fit_pv": "Shoda PV", "fit_mv": "Shoda MV",
        "val_cl_help": "Rozdíly způsobují chyby modelu, neměřené poruchy a to, zda zadané současné parametry odpovídají "
                       "stavu v době záznamu.",

        # chyby
        "err_read": "Soubor nejde načíst: {ex}", "err_data": "Data nejde zpracovat: {ex}",
        "err_time": "Časový sloupec se nepodařilo převést na datum/čas ani na číslo.",
        "err_few": "Některý z vybraných sloupců nemá dost platných hodnot.",
        "err_range": "Horní mez rozsahu musí být větší než dolní.",
        "err_short": "Vybraný úsek je příliš krátký.",
        "err_mv_const": "MV se ve vybraném úseku nemění – model MV → PV z toho nejde určit.",
        "err_fit_failed": "fit se nepodařil.",
        "err_avg_integ": "Průměrovací ladění je určené pro integrační procesy (hladina).",

        # poznámky k ladění
        "note_avg": "Gain = ΔMV/ΔPV_max, TI = 4/(Ki·Gain). Ekvivalentní τc = {tc:.4g} s.",
        "note_avg_aggr": "Pozor: τc < θ – ladění je agresivnější než běžné SIMC, zvaž větší povolenou odchylku hladiny.",
        "note_avg_selfreg": "Proces je samoregulační, použita aproximace Ki ≈ K/T1.",
        "note_p0d": "Proces bez dynamiky – ideálně čistý I regulátor. PIDConL má I složku vázanou na Gain, proto je "
                    "zvolen malý Gain = 0,25/K a TI dopočteno pro stejnou I složku.",
        "note_nod": "Model nemá časovou konstantu pro D složku – navržen PI.",
        "note_half": "PI z redukovaného modelu (pravidlo polovin: T1 + T2/2, θ + T2/2).",
        "note_series": "Sériový tvar Gain={kc:.4g}, TI={ti:.4g}, TD={td:.4g} přepočten na ideální (PIDConL).",
        "note_lag_to_delay": "PI: časová konstanta přičtena k dopravnímu zpoždění.",

        # doporučení D a nové metody
        "d_title": "Doporučení", "tau_label": "θ/(θ+T)", "ratio_label": "T/θ",
        "tau_help": "Normalizované dopravní zpoždění: 0 = čistá setrvačnost, 1 = čisté zpoždění. Rozhoduje o přínosu D "
                    "složky. Počítá se včetně poloviny SampleTime.",
        "ratio_help": "Poměr časové konstanty, kterou může D složka kompenzovat, a dopravního zpoždění. Nad 1 má D smysl.",
        "d_p0d": "Proces bez setrvačnosti (čisté dopravní zpoždění) – D složka nemá co kompenzovat a jen zesiluje šum. "
                 "Použij PI s převahou integrační složky.",
        "d_i0d": "Integrační proces bez časové konstanty – PI obvykle stačí. D přinese jen mírné zrychlení a zvýší šum MV.",
        "d_i1d_yes": "Časová konstanta T1 je větší než dopravní zpoždění – D ji může kompenzovat a výrazně zrychlit "
                     "regulaci, pokud to dovolí šum.",
        "d_i1d_no": "Časová konstanta T1 je menší než dopravní zpoždění – přínos D je malý, PI stačí.",
        "d_p2d_yes": "Druhá časová konstanta T2 je větší než dopravní zpoždění – D ji kompenzuje (TD ≈ T2) a typicky "
                     "přinese výrazné zlepšení.",
        "d_lag": "Setrvačnost výrazně převažuje nad zpožděním (< 0,1) – regulace je snadná a PI stačí. D může zrychlit, "
                 "ale obvykle ho omezí šum a limity ventilu.",
        "d_balanced": "Vyvážený proces (0,1–0,6) – tady přináší D složka největší zlepšení, typicky desítky procent menší "
                      "IAE, pokud to dovolí šum PV.",
        "d_delay": "Dopravní zpoždění převažuje (> 0,6) – D téměř nepomůže, zvol PI. Výrazné zlepšení by přinesl až "
                   "prediktor (Smith) nebo MPC.",
        "noise_note": "Odhad šumu PV z reziduí modelu: σ ≈ {s} {u}. Šum MV v tabulkách je jeho přibližný průchod regulátorem.",
        "m_iSIMC": "iSIMC", "m_AMIGO": "AMIGO", "m_OPT": "Optimalizace",
        "mdesc_SIMC": "Skogestad (2003) – jednoduchá a spolehlivá pravidla s jedním ladicím parametrem τc (výchozí τc = θ).",
        "mdesc_iSIMC": "Zlepšené SIMC (Grimholt & Skogestad 2018) – lepší potlačení poruch u procesů s větším zpožděním, "
                       "PID s TD = θ/3.",
        "mdesc_Lambda": "Lambda / IMC – klidná odezva bez překmitu, v průmyslu oblíbené. Výchozí λ = 3θ. Poruchy potlačuje "
                        "pomaleji.",
        "mdesc_AMIGO": "Åström & Hägglund (2004) – robustní pravidla odvozená z optimalizace pro Ms ≈ 1,4. Bez ladicího "
                       "parametru, spíše konzervativní.",
        "mdesc_OPT": "Numerická optimalizace (MIGO): nejlepší potlačení poruch pro zvolenou robustnost Ms, přímo na "
                     "identifikovaném modelu včetně SampleTime a filtru D. U PID lze omezit šum MV.",
        "mdesc_AVG": "Průměrovací regulace hladiny – maximální využití objemu nádrže, co nejklidnější odtok.",
        "opt_ms": "Robustnost Ms",
        "opt_ms_help": "1,4 = velmi robustní, 1,6 = doporučený kompromis, 2,0 = rychlé, ale citlivé na změny procesu.",
        "opt_noise": "Max. šum MV σ [{u}]",
        "opt_noise_help": "Omezí zesílení D složky, aby šum PV nerozhýbával ventil. 0 = bez omezení.",
        "optimizing": "Optimalizuji…",
        "cmp_title": "Porovnání všech metod", "col_method": "Metoda",
        "iae_load": "IAE poruchy", "iae_sp": "IAE SP", "noise_col": "Šum MV σ [{u}]",
        "cmp_help": "IAE poruchy = odezva na skok 1 % na vstupu procesu, IAE SP = skok SP o 1 % (menší = lepší). "
                    "Porovnávej při podobném Ms. Kliknutím na řádek metodu použiješ.",
        "note_isimc": "Zlepšené SIMC: Gain a TI posunuty o θ/3 – lepší potlačení poruch u procesů s větším zpožděním.",
        "note_isimc_p2d": "Pro PID u modelu 2. řádu je zlepšené SIMC shodné se SIMC (TD = T2).",
        "note_amigo": "AMIGO cílí na Ms ≈ 1,4 – robustní, spíše konzervativní nastavení.",
        "note_amigo_b0": "AMIGO pro tento proces doporučuje P složku ve zpětné vazbě (váha SP b = 0) – klidnější odezva na "
                         "změnu SP.",
        "note_amigo_b1": "AMIGO doporučuje P složku na regulační odchylku (b = 1), θ/(θ+T) = {tau:.2f}.",
        "note_opt": "Optimalizováno pro Ms ≤ {ms}: maximální potlačení poruch (integrační zesílení Gain/TI) při zachování "
                    "robustnosti.",
        "err_opt_failed": "Optimalizace nenašla stabilní řešení – zkus jinou metodu nebo zkontroluj model.",
    },

    "en": {
        "title": "Process identification and PIDConL tuning",
        "empty": "Upload an export from PCS 7 or Process Historian (CSV/Excel) in the sidebar, or try the demo data.",
        "status": "{n} samples · data period {ts} s · length {dur} s · PV {pvr} · MV {mvr}",
        "status_model": "model ready",
        "status_nomodel": "no model fitted yet",
        "tab1": "1 · Data", "tab2": "2 · Model", "tab3": "3 · PIDConL tuning", "tab4": "4 · Validation",
        "time_s": "time [s]", "dists": "disturbances", "fit": "fit", "edited": "edited", "prediction": "prediction",
        "measured": "measured", "simulated": "simulated", "current": "Current", "new": "New",
        "new_err": "New – model error", "setting": "Setting", "resid": "Residual",

        "sb_data": "Data", "source": "Source", "src_file": "File", "src_demo": "Demo",
        "upload": "CSV or Excel from PCS 7 / Process Historian",
        "demo_desc": "Simulated tank: level (integrating process), MV = outlet valve, measured inflow as a "
                     "disturbance. Manual mode with MV steps.",
        "demo_dl": "Download demo data",
        "long_fmt": "Long format (tag, time, value)",
        "long_fmt_help": "Typical historian export – one row = tag, time, value. The app pivots it into columns.",
        "sb_columns": "Columns", "time_unit": "Unit of numeric time",
        "time_unit_help": "Used only when time is a number, not a date.",
        "col_tag": "Tag name column", "col_time": "Time", "col_value": "Value column",
        "col_sp": "SP (optional)", "col_dist": "Measured disturbances (optional)",
        "col_dist_help": "E.g. tank inflow. Improves identification and enables feedforward design.",
        "ts_manual": "Set data period manually", "ts_data": "Data period [s]",
        "sb_norm": "Scaling (NormPV, NormMV)",
        "unit_pv": "PV unit", "unit_mv": "MV unit",
        "norm_help": "Use the same ranges as in the block – Gain then matches the faceplate value directly.",
        "sb_block": "Block configuration", "sampletime": "SampleTime (OB cycle) [s]",
        "sampletime_help": "E.g. OB32 = 1 s, OB35 = 0.1 s – depending on the OB the block runs in.",
        "diffgain_help": "Ratio TD / time constant of the derivative filter.",
        "pfb": "P action in feedback (PV only)",
        "pfb_help": "An SP step then causes no MV kick – smoother SP response, same disturbance rejection.",
        "dfb": "D action in feedback (PV only)",
        "deadband": "Deadband [PV units]", "db_mode": "Deadband", "db_cont": "continuous", "db_step": "step",
        "db_mode_help": "Continuous: the error is reduced by the band width. Step: zero inside the band, full error "
                        "outside. Check how your APL version handles it.",
        "sb_current": "Current parameters (faceplate)", "ti_zero": "TI [s] (0 = no I)",
        "sb_display": "Display", "plot_height": "Chart height [px]",

        "seg_intro": "Select a segment for identification: clear MV changes (steps in manual mode or SP steps in "
                     "auto), no unmeasured disturbances and MV not at its limit.",
        "seg_id": "Identification segment [s]", "mouse": "Mouse in chart",
        "mouse_zoom": "Zoom", "mouse_select": "Select segment",
        "seg_tip": "Tip: in “Select segment” mode drag across the chart and the segment is set automatically. "
                   "Double-click resets zoom. Click a legend item to hide a trace, double-click to show only it.",
        "info_auto": "SP changes in this segment – the data is from auto mode. It is usable if it contains clear SP steps.",
        "warn_limit": "MV is at its limit for {pct} % of the segment – the loop is inactive there and the data carries "
                      "no process information.",
        "warn_irregular": "{name}: timestamps are irregular – the archive is probably compressed. Values between points "
                          "are interpolated and may distort mainly the dead time.",
        "warn_repeated": "{name}: more than half of consecutive values are identical – the data is probably compressed "
                         "or rounded. Consider an export without compression.",

        "models": "Models", "thmax": "Max. θ [s]",
        "thmax_help": "Upper limit of the dead time. The fit tries θ from 0 up to this value – a sensible limit (2–3× the "
                      "expected delay) makes the search more accurate and faster.",
        "run_fit": "Identify", "fitting": "Fitting",
        "info_fit": "Choose models and run the identification.",
        "warn_stale": "Data, segment or settings changed since the last fit – run the identification again.",
        "warn_dists_changed": "The selection of measured disturbances changed since the last fit – run the "
                              "identification again.",
        "col_model": "Model", "col_fit": "Fit",
        "units_note": "Values in % of the scaling ranges: K in %/%, Ki in %/(%·s), Kd in % PV per disturbance unit "
                      "(per second for integrating models). T1, T2, Tp, θ in seconds. Integrating models also fit an "
                      "initial drift.",
        "warn_long_T": "{m}: T1 is longer than the whole data segment – in this range the process behaves practically "
                       "as integrating.",
        "warn_theta_max": "{m}: θ is at the upper limit – raise the limit or check the data.",
        "edit_title": "Model for tuning", "model_for_tuning": "Model",
        "dist_model": "Disturbance model",
        "help_gain": "Process gain (ramp rate for integrating models).",
        "help_T": "Time constant [s].", "help_theta": "Dead time [s].",
        "reset_fit": "Reset to fit", "fit_fit": "Fit – identified", "fit_edit": "Fit – edited",
        "step_title": "Model response to a 10 % MV step",
        "show_resid": "Show residuals (PV − model)",
        "compare_all": "Compare all models",
        "model_P0D": "Zero order (gain + dead time)", "model_P1D": "First order + dead time (FOPDT)",
        "model_P2D": "Second order + dead time (SOPDT)", "model_I0D": "Integrating + dead time",
        "model_I1D": "Integrating + first order + dead time",

        "need_model": "Fit a model in tab 2 · Model first.",
        "samp_note": "SampleTime {s} s ({h} s added to θ)",
        "method": "Method", "m_SIMC": "SIMC", "m_Lambda": "Lambda", "m_AVG": "Averaging",
        "method_help": "The selected method is described below the selector. All methods are compared further down.",
        "ctrl_type": "Controller",
        "avg_dpv": "Max. allowed level deviation [{u}]",
        "avg_dmv": "MV change for the largest disturbance [{u}]",
        "avg_dmv_help": "How much the MV must change to balance the largest expected disturbance.",
        "tc": "Target closed-loop time constant τc / λ [s]",
        "tc_help": "Smaller = faster, more aggressive control; larger = smoother and more robust.",
        "params_title": "PIDConL parameters",
        "params_help": "Prefilled with the suggestion, can be fine-tuned manually. Ideal form: "
                       "MV = Gain·[ER + (1/TI)∫ER dt + TD·dER/dt], derivative lag = TD/DiffGain.",
        "warn_neg_gain": "Gain is negative – the process has a negative gain (e.g. level × outlet valve). Set the "
                         "reverse action in the block according to your APL configuration (negative Gain or inversion).",
        "warn_low_fit": "The model fit is low – treat the parameters as indicative.",
        "ff_title": "Feedforward", "ff_use": "Use for {d}",
        "ff_gain": "FF gain [% MV per 1 unit of {d}]",
        "ff_faster": "{d}: the disturbance acts faster (θd = {td} s) than the MV (θ = {t} s) – static FF will not fully "
                     "compensate it, but will reduce it significantly.",
        "ff_help": "Noise in the disturbance measurement passes straight into the MV via FF – consider a filter. The "
                   "value is in % of MV range per disturbance unit; rescale according to the CFC scaling before wiring "
                   "it to the feedforward input.",
        "compare_title": "Comparison and simulation",
        "ms": "Ms (target 1.4–1.8)", "gm": "Gain margin (target > 2)", "pm": "Phase margin [°] (target > 45)",
        "robust_help": "Ms = peak of the sensitivity function: the smaller, the more robust the loop. Above 2 the loop "
                       "tends to oscillate when the process changes.",
        "err_unstable": "{n}: the loop is unstable according to the model.",
        "scenario": "Scenario", "scen_steps": "SP and disturbance steps", "scen_replay": "Measured disturbances",
        "sim_len": "Length [s]", "sp_step": "SP step [{u}]", "dmv_step": "Unmeasured disturbance [{u}]",
        "dmv_step_help": "Step added to the process input at 40 % of the simulation.",
        "d_step": "Step {d}",
        "replay_help": "Replays the real measured disturbances from the identification segment at constant SP.",
        "robust_on": "Sensitivity to model error (K ×1.3, θ ×1.5)",
        "err_sim_unstable": "{n}: the simulation is unstable.",
        "kpi_maxdev": "Max. PV deviation [{u}]", "kpi_mvrange": "MV range [{u}]",
        "kpi_mvtravel": "Total MV travel [{u}]",
        "kpi_help": "Total MV travel = sum of all output changes, a measure of valve wear. Max. deviation includes SP "
                    "changes.",
        "download": "Download result (CSV)",

        "val_intro": "Validate the model on a different segment than the one it was fitted on. If it matches there "
                     "too, it can be trusted.",
        "seg_val": "Validation segment [s]", "val_mode": "Method",
        "val_pred": "Prediction from MV", "val_cl": "Loop simulation",
        "val_mode_help": "Prediction: the model gets the measured MV and predicts PV – works for any data. Loop "
                         "simulation: model + PIDConL get the measured SP – for segments in auto mode.",
        "fit_pred": "PV prediction fit", "need_sp": "Loop simulation requires an SP column.",
        "val_params": "Parameters", "val_cur": "Current (as the loop ran)", "val_new": "New (what would happen)",
        "fit_pv": "PV fit", "fit_mv": "MV fit",
        "val_cl_help": "Differences come from model errors, unmeasured disturbances, and whether the entered current "
                       "parameters match those active at the time of recording.",

        "err_read": "Cannot read the file: {ex}", "err_data": "Cannot process the data: {ex}",
        "err_time": "The time column could not be converted to date/time or a number.",
        "err_few": "One of the selected columns has too few valid values.",
        "err_range": "The upper range limit must be greater than the lower one.",
        "err_short": "The selected segment is too short.",
        "err_mv_const": "MV does not change in the selected segment – the MV → PV model cannot be identified.",
        "err_fit_failed": "the fit failed.",
        "err_avg_integ": "Averaging tuning is intended for integrating processes (level).",

        "note_avg": "Gain = ΔMV/ΔPV_max, TI = 4/(Ki·Gain). Equivalent τc = {tc:.4g} s.",
        "note_avg_aggr": "Note: τc < θ – the tuning is more aggressive than standard SIMC, consider a larger allowed "
                         "level deviation.",
        "note_avg_selfreg": "The process is self-regulating, approximation Ki ≈ K/T1 used.",
        "note_p0d": "Process without dynamics – ideally a pure I controller. PIDConL ties the I action to Gain, so a "
                    "small Gain = 0.25/K is chosen and TI computed for the same integral action.",
        "note_nod": "The model has no time constant for the D action – PI suggested.",
        "note_half": "PI from a reduced model (half rule: T1 + T2/2, θ + T2/2).",
        "note_series": "Series form Gain={kc:.4g}, TI={ti:.4g}, TD={td:.4g} converted to ideal form (PIDConL).",
        "note_lag_to_delay": "PI: the time constant is added to the dead time.",

        "d_title": "Recommendation", "tau_label": "θ/(θ+T)", "ratio_label": "T/θ",
        "tau_help": "Normalized dead time: 0 = pure lag, 1 = pure delay. Determines the benefit of derivative action. "
                    "Includes half of SampleTime.",
        "ratio_help": "Ratio of the time constant the D action can compensate to the dead time. Above 1, D makes sense.",
        "d_p0d": "Process without lag (pure dead time) – the D action has nothing to compensate and only amplifies noise. "
                 "Use PI with dominant integral action.",
        "d_i0d": "Integrating process without a time constant – PI is usually enough. D brings only a modest speed-up "
                 "and increases MV noise.",
        "d_i1d_yes": "Time constant T1 is larger than the dead time – D can compensate it and speed up control "
                     "significantly, if noise allows.",
        "d_i1d_no": "Time constant T1 is smaller than the dead time – the benefit of D is small, PI is enough.",
        "d_p2d_yes": "The second time constant T2 is larger than the dead time – D compensates it (TD ≈ T2) and usually "
                     "brings a significant improvement.",
        "d_lag": "Lag clearly dominates the delay (< 0.1) – control is easy and PI is enough. D can speed things up, but "
                 "is usually limited by noise and valve limits.",
        "d_balanced": "Balanced process (0.1–0.6) – this is where D brings the largest improvement, typically tens of "
                      "percent lower IAE, if PV noise allows.",
        "d_delay": "Dead time dominates (> 0.6) – D will hardly help, choose PI. A significant improvement would need a "
                   "predictor (Smith) or MPC.",
        "noise_note": "PV noise estimated from model residuals: σ ≈ {s} {u}. MV noise in the tables is its approximate "
                      "propagation through the controller.",
        "m_iSIMC": "iSIMC", "m_AMIGO": "AMIGO", "m_OPT": "Optimization",
        "mdesc_SIMC": "Skogestad (2003) – simple, reliable rules with one tuning parameter τc (default τc = θ).",
        "mdesc_iSIMC": "Improved SIMC (Grimholt & Skogestad 2018) – better disturbance rejection for processes with "
                       "larger delay, PID with TD = θ/3.",
        "mdesc_Lambda": "Lambda / IMC – smooth response without overshoot, popular in industry. Default λ = 3θ. Slower "
                        "disturbance rejection.",
        "mdesc_AMIGO": "Åström & Hägglund (2004) – robust rules derived from optimization for Ms ≈ 1.4. No tuning "
                       "parameter, rather conservative.",
        "mdesc_OPT": "Numerical optimization (MIGO): best disturbance rejection for the chosen robustness Ms, directly on "
                     "the identified model including SampleTime and the D filter. For PID, MV noise can be limited.",
        "mdesc_AVG": "Averaging level control – maximum use of tank volume, smoothest possible outflow.",
        "opt_ms": "Robustness Ms",
        "opt_ms_help": "1.4 = very robust, 1.6 = recommended compromise, 2.0 = fast but sensitive to process changes.",
        "opt_noise": "Max. MV noise σ [{u}]",
        "opt_noise_help": "Limits the derivative gain so that PV noise does not move the valve. 0 = no limit.",
        "optimizing": "Optimizing…",
        "cmp_title": "Compare all methods", "col_method": "Method",
        "iae_load": "IAE disturbance", "iae_sp": "IAE SP", "noise_col": "MV noise σ [{u}]",
        "cmp_help": "IAE disturbance = response to a 1 % step at the process input, IAE SP = 1 % SP step (lower = "
                    "better). Compare at similar Ms. Click a row to use that method.",
        "note_isimc": "Improved SIMC: Gain and TI shifted by θ/3 – better disturbance rejection for processes with "
                      "larger delay.",
        "note_isimc_p2d": "For PID on a second-order model, improved SIMC equals SIMC (TD = T2).",
        "note_amigo": "AMIGO targets Ms ≈ 1.4 – robust, rather conservative tuning.",
        "note_amigo_b0": "For this process AMIGO recommends P action in feedback (setpoint weight b = 0) – smoother "
                         "response to SP changes.",
        "note_amigo_b1": "AMIGO recommends P action on the control error (b = 1), θ/(θ+T) = {tau:.2f}.",
        "note_opt": "Optimized for Ms ≤ {ms}: maximum disturbance rejection (integral gain Gain/TI) while keeping "
                    "robustness.",
        "err_opt_failed": "The optimization found no stable solution – try another method or check the model.",
    },
}


# doplňky v4
from i18n_extra import CS as _CS, EN as _EN  # noqa: E402
TEXTS["cs"].update(_CS)
TEXTS["en"].update(_EN)
