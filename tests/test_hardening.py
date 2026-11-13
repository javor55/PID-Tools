"""Zabezpečení všech režimů: hlavičky, logo SVG, meze vstupů (CSV / XLSX / projekt), limity programu regulátoru."""
import io
import zipfile

import pandas as pd
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.app import dataio  # noqa: E402
from pidtools.controllers.program import LIMITS, ProgramErrors, compile_program  # noqa: E402

V1 = "/api/v1"


def test_security_headers_in_desktop_mode():
    with TestClient(create_app(token="t")) as c:
        for path in ("/health", f"{V1}/health", "/"):
            h = c.get(path).headers
            csp = h["content-security-policy"]
            for part in ("default-src 'self'", "script-src 'self'", "frame-ancestors 'none'", "base-uri 'none'",
                         "form-action 'self'", "connect-src 'self'", "img-src 'self' data: blob:"):
                assert part in csp
            assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
            assert h["referrer-policy"] == "no-referrer" and h["cross-origin-opener-policy"] == "same-origin"
            assert "permissions-policy" in h
        assert "strict-transport-security" not in c.get("/health").headers      # HSTS jen za HTTPS veřejného režimu
        assert "content-security-policy" not in c.get("/docs").headers          # Swagger UI potřebuje CDN


def test_svg_logo_not_accepted_and_old_one_served_as_attachment(tmp_path):
    cfgd = tmp_path / "c"
    cfgd.mkdir()
    (cfgd / "logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    (cfgd / "settings.json").write_text('{"format":"pidtools.settings","version":1,"settings":{"report":{"logo":"logo.svg"}}}')
    with TestClient(create_app(config_dir=str(cfgd), data_dir=str(tmp_path / "d"))) as c:
        assert c.post(f"{V1}/app-settings/logo?name=l.svg", content=b"<svg/>").status_code == 422
        r = c.get(f"{V1}/app-settings/logo")
        assert r.status_code == 200
        assert r.headers["content-disposition"].startswith("attachment")
        assert "sandbox" in r.headers["content-security-policy"] and "default-src 'none'" in r.headers["content-security-policy"]
        assert c.post(f"{V1}/app-settings/logo?name=l.png", content=b"\x89PNG").status_code == 200
        assert "attachment" not in c.get(f"{V1}/app-settings/logo").headers.get("content-disposition", "")


# ---- meze vstupů
def _xlsx(df):
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def test_xlsx_ok_and_limits(monkeypatch):
    df = pd.DataFrame({"t": range(10), "y": range(10)})
    raw = _xlsx(df)
    assert dataio.read_table("a.xlsx", raw).shape == (10, 2)
    with monkeypatch.context() as m:
        m.setattr(dataio, "MAX_XLSX_UNPACKED", 1000)                            # součet rozbalených velikostí
        with pytest.raises(ValueError, match="data_too_big"):
            dataio.read_table("a.xlsx", raw)
    with monkeypatch.context() as m:
        m.setattr(dataio, "MAX_ROWS", 5)
        with pytest.raises(ValueError, match="data_too_big"):
            dataio.read_table("a.xlsx", raw)
        with pytest.raises(ValueError, match="data_too_big"):
            dataio.read_table("a.csv", b"t,y\n" + b"1,2\n" * 50)
    with monkeypatch.context() as m:
        m.setattr(dataio, "MAX_COLS", 3)
        with pytest.raises(ValueError, match="data_too_big"):
            dataio.read_table("a.csv", b"a,b,c,d\n1,2,3,4\n5,6,7,8\n")


def test_zip_bomb_rejected_before_parsing():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr("xl/worksheets/sheet1.xml", b"0" * (dataio.MAX_XLSX_UNPACKED + 1))    # ≈ 130 MB nul, v zipu pár stovek kB
    assert len(buf.getvalue()) < 2 ** 20
    with pytest.raises(ValueError, match="data_too_big"):
        dataio.read_table("bomb.xlsx", buf.getvalue())
    with pytest.raises(ValueError, match="data_bad_xlsx"):
        dataio.read_table("junk.xlsx", b"not a zip")


def test_upload_errors_are_translatable_keys():
    with TestClient(create_app(token="t")) as c:
        w = c.post(f"{V1}/workspaces", headers={"X-PID-Token": "t"}).json()["id"]
        r = c.post(f"{V1}/workspaces/{w}/data/file?name=x.xlsx", content=b"junk", headers={"X-PID-Token": "t"})
        assert r.status_code == 400 and r.json()["detail"] == "data_bad_xlsx"


def test_project_deep_json_is_400_not_500():
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        w = c.post(f"{V1}/workspaces").json()["id"]
        r = c.put(f"{V1}/workspaces/{w}/project", content=b"[" * 500_000)
        assert r.status_code == 400 and "Traceback" not in r.text


# ---- program regulátoru
def test_program_limits():
    with pytest.raises(ProgramErrors) as e:
        compile_program("MV = " + "SP + " * 6000 + "PV")                         # zdroj nad LIMITS["source"]
    assert e.value.errors[0].code == "too_big"
    with pytest.raises(ProgramErrors) as e:
        compile_program("\n".join(f"param p{i} = 1" for i in range(LIMITS["params"] + 5)) + "\nMV = SP - PV")
    assert e.value.errors
    with pytest.raises(ProgramErrors) as e:
        compile_program("MV = " + "(" * 500 + "PV" + ")" * 500)                  # hloubka výrazu
    assert {x.code for x in e.value.errors} & {"too_deep", "too_big"}
    with pytest.raises(ProgramErrors) as e:
        compile_program("MV = " + " + ".join(["(SP - PV)"] * 400))                # počet uzlů / hloubka řetězu
    assert e.value.errors
