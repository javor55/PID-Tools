"""Načtení dat: formáty času, sloupce času u každé veličiny a odhad role sloupců."""
import numpy as np
import pandas as pd
import pytest

from pidtools.app.dataio import detect_time_format, pair_time_columns, pairs_to_wide, parse_time, time_columns
from pidtools.app.guess import guess_roles


@pytest.mark.parametrize("values, kind, step", [
    (["1.2.2024 13:00:00", "1.2.2024 13:00:01", "1.2.2024 13:00:02"], "cz", 1.0),
    (["1. 2. 2024 13:00", "1. 2. 2024 13:01", "1. 2. 2024 13:02"], "cz", 60.0),
    (["13.02.2024 23:59:59,500", "14.02.2024 00:00:00,000", "14.02.2024 00:00:00,500"], "cz", 0.5),
    (["2/13/2024 1:00:00 PM", "2/13/2024 1:00:01 PM", "2/13/2024 1:00:02 PM"], "us", 1.0),
    (["2024-02-13T13:00:00Z", "2024-02-13T13:00:01Z", "2024-02-13T13:00:02Z"], "iso", 1.0),
    (["01/02/2024 10:00", "02/02/2024 10:00", "03/02/2024 10:00", "04/02/2024 10:00"], "eu", 86400.0),
    (["23:59:58", "23:59:59", "00:00:00", "00:00:01"], "clock", 1.0),
    (["0,0", "0,5", "1,0"], "num", 0.5),
])
def test_time_formats(values, kind, step):
    col = pd.Series(values)
    assert detect_time_format(col)[0] == kind
    assert np.allclose(np.diff(parse_time(col)[0]), step)


def test_forced_time_format():
    col = pd.Series(["01/02/2024 10:00", "02/02/2024 10:00"])
    assert np.diff(parse_time(col, fmt="us")[0])[0] == pytest.approx(31 * 86400)
    assert np.diff(parse_time(col, fmt="eu")[0])[0] == pytest.approx(86400)


def test_time_per_variable():
    """Export „čas, hodnota, čas, hodnota“ s různě dlouhými sloupci → jedna tabulka se sjednocenými časy."""
    df = pd.DataFrame({
        "Time PV": ["1.2.2024 13:00:00", "1.2.2024 13:00:01", "1.2.2024 13:00:02", "1.2.2024 13:00:03"],
        "LIC1.PV": [1.0, 2.0, 3.0, 4.0],
        "Time OP": ["1.2.2024 13:00:00.5", "1.2.2024 13:00:02.5", None, None],
        "LIC1.OP": [5.0, 6.0, None, None]})
    tc = time_columns(df)
    assert tc == ["Time PV", "Time OP"]
    pairs = pair_time_columns(df, tc)
    assert pairs == {"LIC1.PV": "Time PV", "LIC1.OP": "Time OP"}
    wide, origin = pairs_to_wide(df, pairs)
    assert len(wide) == 6 and wide["LIC1.PV"].notna().sum() == 4 and wide["LIC1.OP"].notna().sum() == 2
    assert origin is not None


def test_numeric_time_column_needs_name_and_monotonic():
    df = pd.DataFrame({"t": [0, 1, 2, 3], "T": [50, 49, 51, 50], "x": [1, 2, 3, 4]})
    assert time_columns(df) == ["t"]


@pytest.mark.parametrize("sigs, pv, mv, sp", [
    (["FIC100.PV", "FIC100.OP", "LIC200.PV", "LIC200.OP", "FIC100.SP"], "FIC100.PV", "FIC100.OP", "FIC100.SP"),
    (["TIC_01_CV", "TIC_01_SV", "TIC_01_MV"], "TIC_01_CV", "TIC_01_MV", "TIC_01_SV"),
    (["PIC5.X", "PIC5.Y", "PIC5.W"], "PIC5.X", "PIC5.Y", "PIC5.W"),
    (["LIC101PV", "LIC101MV", "LIC101SP"], "LIC101PV", "LIC101MV", "LIC101SP"),
    (["Teplota", "Ventil", "Zadana teplota"], "Teplota", "Ventil", "Zadana teplota"),
    (["TIC101/PV.Value", "TIC101/OUT.Value"], "TIC101/PV.Value", "TIC101/OUT.Value", None),
])
def test_guess_roles(sigs, pv, mv, sp):
    g = guess_roles(sigs)
    assert (g["pv"], g["mv"], g["sp"]) == (pv, mv, sp)


def test_guess_roles_valve_position():
    assert guess_roles(["PIC5.X", "PIC5.Y", "PIC5.Y_POS"])["pos"] == "PIC5.Y_POS"


def test_csv_encodings():
    """Exporty z českých Windows (windows-1250), Excel / WinCC „Unicode text“ (UTF-16 s BOM) a UTF-8 s BOM."""
    from pidtools.app.dataio import read_table
    text = "Čas;Teplota °C;Ventil %\n0;51,5;40\n1;51,7;41\n"
    for enc, bom in (("cp1250", b""), ("utf-16-le", b"\xff\xfe"), ("utf-8", b"\xef\xbb\xbf"), ("utf-8", b"")):
        df = read_table("export.csv", bom + text.encode(enc))
        assert list(df.columns) == ["Čas", "Teplota °C", "Ventil %"], enc
        assert df.iloc[1, 1] == 51.7
