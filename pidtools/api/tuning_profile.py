"""
API – ladění podle profilu regulátoru smyčky (E8-B): tabulka robustnosti sad, varování ladění (T3–T5), proces a ventil
v simulaci (T2) a export sady v názvech a jednotkách bloku (PCS 7 / TIA / DeltaV / CSV). Návrh a sady v jednotkách
bloku jsou součástí `/tuning` (`api.tuning`).
"""
from fastapi import APIRouter, HTTPException, Response

from .. import i18n
from ..app import tuning_export as tex
from .tuning import Pid, PlantInfo, PlantSet, RobRow, Warn, _fin


def router(get_proj):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["tuning"])

    def need_model(wid):
        ws = get_proj(wid).state
        if not ws.has_data:
            raise HTTPException(409, "no data")
        if ws.model is None:
            raise HTTPException(409, "no model")
        return ws

    @r.post("/tuning/robustness", response_model=list[RobRow])
    def robustness(wid: str, preview: Pid | None = None):
        """Tabulka robustnosti sad (Set 1, Set 2, návrh): Ms, Mt, GM, PM, šum MV a nejhorší Ms přes nejistotu modelu."""
        ws = need_model(wid)
        cs = {"set1": ws.set_ctrl(1), "set2": ws.set_ctrl(2)}
        if preview is not None:
            cs["sug"] = ws.ctrl_of(preview.model_dump())
        out = []
        for k, c in cs.items():
            m = ws.ctrl_metrics(c, mt=True)
            st = bool(m["stable"])
            out.append(RobRow(name=k, stable=st, Ms=_fin(m["Ms"]) if st else None, Mt=_fin(m.get("Mt")) if st else None,
                              GM=_fin(m["GM"]) if st else None, PM=_fin(m["PM"]) if st else None, noise=_fin(m["noise"]),
                              Ms_worst=_fin(m.get("Ms_worst")), approximate=bool(m.get("approximate"))))
        return out

    @r.get("/tuning/warnings", response_model=list[Warn])
    def warnings(wid: str):
        """Varování ladění: data mimo NormPV / NormMV, pracovní bod MV mimo limity, nízká shoda modelu."""
        return [Warn(key=k, text=i18n.T(k, **a)) for k, a in need_model(wid).tuning_warnings()]

    @r.get("/tuning/plant", response_model=PlantInfo)
    def get_plant(wid: str):
        """Proces a ventil v simulaci (Ladění i Živá): stikce, skluz, šum PV, charakteristika ventilu."""
        return PlantInfo(**need_model(wid).plant_view())

    @r.put("/tuning/plant", response_model=PlantInfo)
    def set_plant(wid: str, body: PlantSet):
        ws = need_model(wid)
        if body.vchar is not None and (len(body.vchar) != 10 or min(body.vchar) < 0):
            raise HTTPException(422, "vchar: 10 non-negative gains")
        ch = {}
        if body.stic is not None:
            ch[ws.stic_key] = max(0.0, body.stic)
        if body.slip is not None:
            ch["sim_J"] = min(100.0, max(0.0, body.slip))
        if body.noise is not None:
            ch["sim_noise"] = max(0.0, body.noise)
        if body.vchar is not None:
            ch["vchar_last"] = [float(v) for v in body.vchar]
        ws.set(**ch)
        return get_plant(wid)

    @r.get("/tuning/export", response_class=Response,
           responses={200: {"content": {"text/plain": {}, "text/csv": {}},
                            "description": "parameter set in block names and units (fmt: csv, pcs7, tia, deltav)"}})
    def export(wid: str, fmt: str = "csv", n: int = 2):
        """Export sady `n` (výchozí Set 2) v názvech a jednotkách bloku regulátoru smyčky pro řídicí systém / CSV."""
        ws = need_model(wid)
        if fmt not in tex.FORMATS or n not in (1, 2):
            raise HTTPException(422, f"unknown export format: {fmt}")
        f = tex.FORMATS[fmt]
        ctx = ws.export_ctx(n)
        ctx["dec"] = i18n.decimal()
        return Response(tex.export(fmt, ctx), media_type=f"{f['mime']}; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="tuning_set{n}_{fmt}.{f["ext"]}"'})

    return r
