"""
Výpočty pokročilých regulačních struktur (APC) pro frontendy – nad pidtools.core.apc a core.gainsched.

Smyčka se předává jako záznam (dict) se stejnými klíči jako ve webové aplikaci (`ui.loops.loop_data`):
name, model (kód, parametry, parametry poruch), ctrl (sada 2), c_pv, c_mv, c_sp, c_d (měřené poruchy),
pv_rng, mv_rng (rozsahy regulátoru), u_pv, u_mv (jednotky).

Moduly:
  common       – charakteristický čas, mřížka simulace, vzájemné vazby smyček
  recommend    – doporučení struktur podle modelů a vazeb mezi smyčkami
  smith        – Smithův prediktor: τc, hodnoty pro šablonu SmithPredictorControl
  gainsched    – gain scheduling podle PV (pracovní body) a podle regulační odchylky
  feedforward  – hodnoty dopředné vazby pro PIDConL (FFwd)
  decouple     – zesílení decouplerů v inženýrských jednotkách
"""
