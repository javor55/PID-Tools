"""
Registr zdrojů dat (plán v2, kap. 7): CSV, TXT, XLSX / XLS a OPC UA. Další zdroj (PI Web API, historian REST …)
= jedna položka s funkcí `fn(name, raw, frame) → pandas.DataFrame`, schématem parametrů, popisem v i18n a ukázkou
pro test (`tests/test_domain_sources.py` projde všechny položky).

Čtení souborů se nepřepisuje: používá se `app.dataio.read_table`; rozložení tabulky (wide / pairs / long, čas, jednotka)
řeší `app.dataset.signals` podle voleb zdroje. OPC UA dodá tabulku už hotovou (import z `app.opc` v dlouhém formátu).
"""
import io

import pandas as pd

from ...i18n import T
from .. import registry as reg
from ..dataio import ROWS, TIME_FORMATS, read_table
from ..dataset import LAYOUTS, UNITS

# volby čtení tabulky společné všem zdrojům (klíče Source.options)
READ_PARAMS = {
    "layout": dict(type="choice", choices=list(LAYOUTS), default=None, desc="src_p_layout"),
    "time_fmt": dict(type="choice", choices=list(TIME_FORMATS), default="auto", desc="src_p_time_fmt"),
    "unit": dict(type="choice", choices=list(UNITS), default="s", desc="src_p_unit"),
    "c_time": dict(type="column", default=None, desc="src_p_c_time", note=f"{ROWS} = no time column"),
    "c_tag": dict(type="column", default=None, desc="src_p_c_tag"),
    "c_val": dict(type="column", default=None, desc="src_p_c_val"),
    "row_dt": dict(type="number", default=1.0, desc="src_p_row_dt"),
}

SOURCES = reg.Registry("source")


def _file(name, raw, frame):
    if raw is None:
        raise ValueError(T("err_source_raw"))
    return read_table(name, raw)


def _opc(name, raw, frame):
    if not isinstance(frame, pd.DataFrame) or len(frame) < 2:
        raise ValueError(T("err_source_frame"))
    return frame


def _sample_csv():
    return dict(name="a.csv", raw=b"Time,TIC101.PV,TIC101.OUT\n0,1,2\n1,2,2\n2,3,2\n3,4,3\n4,5,3\n")


def _sample_xlsx():
    df = pd.DataFrame({"Time": range(5), "TIC101.PV": [1.0, 2, 3, 4, 5], "TIC101.OUT": [2.0, 2, 2, 3, 3]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return dict(name="a.xlsx", raw=buf.getvalue())


def _sample_opc():
    t = pd.date_range("2026-01-01", periods=6, freq="s")
    return dict(name="OPC UA", frame=pd.DataFrame({"Tag": ["TIC101.PV"] * 6, "Time": t, "Value": range(6)}))


SOURCES.register("csv", "src_csv", _file, READ_PARAMS, exts=(".csv", ".tsv"), sample=_sample_csv)
SOURCES.register("txt", "src_txt", _file, READ_PARAMS, exts=(".txt", ".dat", ".prn"), sample=lambda: dict(
    name="a.txt", raw=b"Time;TIC101.PV;TIC101.OUT\n0;1,5;2\n1;2,5;2\n2;3,5;2\n3;4,5;3\n4;5,5;3\n"))
SOURCES.register("xlsx", "src_xlsx", _file, READ_PARAMS, exts=(".xlsx", ".xls"), sample=_sample_xlsx)
SOURCES.register("opc", "src_opc", _opc, READ_PARAMS, exts=(), sample=_sample_opc)


def kind_for(name):
    """Druh zdroje podle přípony souboru (neznámá přípona = textový CSV s odhadem oddělovače)."""
    low = str(name).lower()
    for e in SOURCES.items():
        if low.endswith(tuple(e.meta["exts"])):
            return e.id
    return "csv"


def load(kind, name, raw=None, frame=None):
    """Zdroj → tabulka (`pandas.DataFrame`) podle druhu v registru; neznámý druh → ValueError s textem."""
    if kind not in SOURCES:
        raise ValueError(T("err_source_kind", kind=kind))
    return SOURCES.get(kind).fn(name, raw, frame)
