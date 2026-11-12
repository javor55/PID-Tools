"""
Katalog částí regulátoru (R3, docs/cs/regulatory.md § 4): pro každou položku registrů `core.controller` její popis (klíč
i18n `ctl_part_<registr>_<id>`) a schéma parametrů (role, jednotka, výchozí hodnota, rozsah). Čistá data – editor
regulátoru z nich skládá nabídku částí, test hlídá, že katalog pokrývá všechny hotové položky registrů.
"""
__all__ = ["PARTS", "describe"]


def _p(role, unit="-", default=0.0, rng=None):
    return dict(role=role, unit=unit, default=default, range=rng)


PARTS = {
    "forms": {"ideal": [], "parallel": [], "series": []},
    "deadbands": {
        "continuous": [_p("deadband", "%", 0.0, [0, 100])],
        "step": [_p("deadband", "%", 0.0, [0, 100])],
        "gap": [_p("deadband", "%", 0.0, [0, 100]), _p("gap_gain", "-", 0.3, [0, 1])],
    },
    "d_sources": {"error": [], "pv": [], "error_or_pv": [_p("d_on_pv", "bool", False)]},
    "d_filters": {"td_over_n": [_p("N", "-", 5.0, [1e-6, 1000])], "none": [], "fixed": [_p("Tf", "s", 0.0, [0, 1e6])]},
    "antiwindups": {
        "clamp_conditional": [], "none": [],
        "back_calculation": [_p("Tt", "s", 10.0, [1e-6, 1e6])],
        "external_reset": [_p("Tt", "s", 0.0, [0, 1e6])],
    },
    "algorithms": {"position": [], "velocity": []},
    "normalisations": {"percent": []},
    "pv_filters": {"lag1": [_p("pv_filter", "s", 0.0, [0, 1e6])], "none": []},
    "nl_gains": {
        "none": [],
        "squared": [_p("nl_e0", "%", 5.0, [0, 100])],
        "table": [],        # tabulka x / y a vstup (pv, sp, mv, error) jsou ve `structure.error.nonlinear`
    },
    "output_stages": {
        "none": [],
        "split_range": [_p("split_point", "%", 50.0, [0, 100]), _p("split_gap", "%", 0.0, [0, 100]),
                        _p("k_heat", "-", 1.0, [0, 100]), _p("k_cool", "-", 1.0, [0, 100])],
        "three_step": [_p("motor_time", "s", 60.0, [1e-6, 1e6]), _p("tri_threshold", "%", 1.0, [0, 100]),
                       _p("min_pulse", "s", 0.0, [0, 1e6]), _p("min_pause", "s", 0.0, [0, 1e6])],
        "pwm": [_p("pwm_period", "s", 10.0, [1e-6, 1e6]), _p("min_pulse", "s", 0.0, [0, 1e6])],
    },
}


def describe():
    """Katalog jako seznam [{kind, id, desc_key, params}] (pro API / editor)."""
    return [dict(kind=k, id=i, desc_key=f"ctl_part_{k}_{i}", params=params)
            for k, items in PARTS.items() for i, params in items.items()]
