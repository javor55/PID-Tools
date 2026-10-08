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
    (["Aug-04-07 20:47:20", "Aug-04-07 20:47:21", "Aug-04-07 20:47:22"], "mon", 1.0),
    (["04-Aug-2007 20:47:20", "04-Aug-2007 20:47:30", "04-Aug-2007 20:47:40"], "mon", 10.0),
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


def test_quoted_lines_csv():
    """Export, kde je celý řádek v uvozovkách a vnitřní uvozovky zdvojené (IP.21 přes Excel) → normální sloupce."""
    from pidtools.app.dataio import read_table
    rows = ['"Sample Time,""LT1.PV IP"",""LT1.MV IP"""'] + [
        f'"2026-09-29T09:06:{i:02d}.230000Z,""{16 + 0.1 * i:.4f}"",""{99 - i:.4f}"""' for i in range(30)]
    df = read_table("x.csv", ("\ufeff" + "\n".join(rows)).encode("utf-8"))
    assert list(df.columns) == ["Sample Time", "LT1.PV IP", "LT1.MV IP"] and len(df) == 30
    from pidtools.app import dataset as ds
    sg = ds.signals(df)
    assert sg.time_src == ["Sample Time"] and np.allclose(np.diff(sg.t_all), 1.0)


def test_rows_as_samples():
    """Čas nerozpoznaný nebo konstantní → co řádek, to vzorek (perioda zadaná ručně, i v ms / min)."""
    from pidtools.app import dataset as ds
    from pidtools.app.dataio import ROWS
    n = 50
    df = pd.DataFrame({"Time": ["Aug-04-07 20:47:20"] * n, "CV": np.linspace(50, 60, n), "MV1": np.ones(n)})
    sg = ds.signals(df)
    assert sg.time_src == [ROWS] and sg.time_note == "rows_auto" and sg.sigs == ["CV", "MV1"]
    assert sg.t_all[1] == 1.0 and sg.t_all[-1] == n - 1
    sg = ds.signals(df, unit="ms", c_time=ROWS, row_dt=500)
    assert sg.t_all[1] == pytest.approx(0.5) and sg.time_note == ""
    sg = ds.signals(df, unit="min", c_time=ROWS, row_dt=2)
    assert sg.t_all[1] == pytest.approx(120.0)
    with pytest.raises(ValueError):
        parse_time(df["Time"])


def test_wincc_trend_export():
    """Export trendu WinCC: UTF-16, středníky, dvojice „X Time“ / „X ValueY“ s US časem, nepoužité křivky prázdné."""
    from pidtools.app import dataset as ds
    from pidtools.app.dataio import read_table
    head = '"PV_Out Time";"PV_Out ValueY";"SP Time";"SP ValueY";"Tol Time";"Tol ValueY";"MV Time";"MV ValueY"'
    rows = [f"10/4/2026 2:19:{i:02d} PM;{0.1 * i:.2f};10/4/2026 2:19:{i:02d} PM;15;;;10/4/2026 2:19:{i:02d} PM;{40 + i}"
            for i in range(60)]
    raw = ("﻿" + "\r\n".join([head] + rows) + "\r\n").encode("utf-16-le")
    df = read_table("trend.csv", b"\xff\xfe" + raw[2:])
    assert "Tol Time" not in df.columns and len(df) == 60
    sg = ds.signals(df, ds.default_layout(df))
    assert sg.sigs == ["PV_Out", "SP", "MV"] and sg.t_all[-1] == pytest.approx(59.0)


def test_decimate_keeps_gaps():
    """Zředění pro graf funguje i s mezerami (NaN): špičky zůstanou, prázdné bloky zůstanou prázdné."""
    from pidtools.app.plots import decimate
    x = np.arange(100000.0)
    y = np.sin(x / 1000)
    y[:30000] = np.nan
    y[50000] = 5.0
    xs, ys = decimate(x, y)
    assert len(xs) <= 2100 and np.nanmax(ys) == 5.0 and np.isnan(ys[:100]).all()


def test_chart_values_keep_decimals():
    """Graf na webu: velké hodnoty s malými změnami (tlak 101 325 Pa ± 0,5) si zachovají desetiny."""
    from pidtools.app.plots import _short, tr
    p = 101325 + 0.37 * np.arange(10)
    assert np.allclose(_short(p), p)
    y = np.r_[50 + 0.37 * np.arange(9), 99999.0]               # odlehlý bod nerozhoduje
    assert np.allclose(_short(y), y)
    t = tr(np.arange(10.0), p, "PV", "#000")
    assert np.allclose(np.asarray(t.y, float), p)
    c = np.full(5, 101325.25)
    assert np.array_equal(_short(c), c)
