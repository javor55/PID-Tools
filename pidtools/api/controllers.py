"""
API – knihovna regulátorů a profil regulátoru smyčky (E7, docs/cs/regulatory.md): seznam předvoleb a vlastních profilů,
vytvoření vlastního z předvolby („Vytvořit vlastní“ = kopie), změna a smazání vlastního, import / export `.pidctrl`,
mapování kanonického PID na parametry profilu a zpět, test použitelnosti (protokol) a kopie profilu v projektu
(`/workspaces/{wid}/controller`, výchozí PIDConL), katalog částí (`/parts`, R3) a překlad vlastních rovnic
(`POST /compile`, R4: zdroj → chyby s řádkem a sloupcem, nebo program, parametry a rychlé kontroly). Vlastní program
(`kind = program`, `source`) se ukládá stejnými koncovými body jako skládaný profil.
"""
import hashlib
import json
import math
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from .. import i18n
from ..app import controller_check
from ..controllers import Library, ProfileError, canonical_to_profile, load_preset, profile_to_canonical, validate_profile
from ..controllers.loader import FORMAT, VERSION
from ..controllers.parts import describe as describe_parts
from ..controllers.program import ProgramErrors, compile_program, has_mapping, tuning_roles
from ..core.controller import make_profile

DEFAULT_ID = "pcs7_pidconl"
MAX_PROFILE = 2 ** 20


class ControllerParam(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: str
    role: str
    name: str | None = None
    unit: str | None = None
    repr: str | None = None
    required: bool | None = None
    nullable: bool | None = None
    default: Any = None
    range: list[float] | None = None


class ControllerProfile(BaseModel):
    """Profil regulátoru (soubor `.pidctrl`); neznámé položky (struktura, ověření, výsledek testu) se zachovají."""
    model_config = ConfigDict(extra="allow")
    format: str = FORMAT
    version: int = VERSION
    id: str | None = None
    name: str | None = None
    vendor: str | None = None
    system: str | None = None
    block: str | None = None
    derived_from: str | None = None
    verification: dict[str, Any] | None = None
    kind: str | None = None                     # "program" = vlastní rovnice (`source`), jinak skládaný profil
    source: str | None = None
    structure: dict[str, Any] = {}
    params: list[ControllerParam] = []          # u programu se odvodí ze zdroje


class ControllerSummary(BaseModel):
    id: str
    vendor: str
    name: str
    tag: str                      # preset / custom
    verified: bool


class CheckItem(BaseModel):
    id: str
    name: str
    status: str                   # ok / warn / fail
    severity: str                 # critical / mapping / info
    message: str
    rows: list[dict[str, Any]] | None = None


class CheckProtocol(BaseModel):
    verdict: str                  # suitable / optimisation_only / unsuitable
    verdict_text: str
    checks: list[CheckItem]
    reasons: list[str]


class PartParam(BaseModel):
    role: str
    unit: str
    default: Any = None
    range: list[float] | None = None


class PartInfo(BaseModel):
    kind: str                     # registr: forms, deadbands, antiwindups, algorithms, nl_gains, output_stages …
    id: str
    description: str
    params: list[PartParam]


class CompileRequest(BaseModel):
    source: str
    quick: bool = True            # rychlé kontroly testu použitelnosti (překlad, determinismus, klid, numerika, výkon)


class SourceIssue(BaseModel):
    line: int
    col: int
    code: str
    message: str


class CompileResult(BaseModel):
    ok: bool
    errors: list[SourceIssue]
    warnings: list[SourceIssue]
    program: dict[str, Any] | None = None
    params: list[ControllerParam] | None = None
    tuning_roles: list[str] | None = None
    has_mapping: bool | None = None
    checks: CheckProtocol | None = None


class NewController(BaseModel):
    from_id: str
    name: str | None = None


class Ranges(BaseModel):
    pv_range: list[float] | None = None
    mv_range: list[float] | None = None


class CanonicalPID(BaseModel):
    Kc: float
    Ti: float | None = None       # None = bez I složky
    Td: float = 0.0
    b: float = 1.0
    c: float = 1.0
    N: float | None = 5.0         # None = bez filtru


class MapRequest(Ranges):
    canonical: CanonicalPID


class Warning_(BaseModel):
    key: str
    text: str


class MapResult(BaseModel):
    values: dict[str, Any]
    warnings: list[Warning_]
    effective: CanonicalPID


class CanonicalRequest(Ranges):
    values: dict[str, Any]


class LoopController(BaseModel):
    profile: ControllerProfile
    is_default: bool
    checksum: str


class LoopControllerPut(BaseModel):
    from_id: str | None = None                  # kopie z knihovny
    profile: ControllerProfile | None = None    # nebo vlastní profil; bez obojího = výchozí PIDConL


def _issue(e, prefix):
    return SourceIssue(line=e.line, col=e.col, code=e.code, message=i18n.T(f"{prefix}_{e.code}", **e.info))


def _num(x):
    """JSON nezná nekonečno: bez I složky / bez filtru je None."""
    return x if (x is not None and math.isfinite(x)) else None


def _canon(c):
    return CanonicalPID(**{k: _num(v) if k in ("Ti", "N") else v for k, v in c.items()})


def _checksum(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _compile(data):
    """Schéma i překlad profilu (registry částí); 422 s popisem problému."""
    try:
        bad = validate_profile(data)
        if bad:
            raise ProfileError(bad)
        make_profile(data)
    except ProfileError as ex:
        raise HTTPException(422, dict(message=str(ex), problems=ex.problems)) from ex
    except (ValueError, KeyError, NotImplementedError) as ex:
        raise HTTPException(422, dict(message=str(ex), problems=[dict(path="", message=str(ex))])) from ex


def _body(profile):
    return profile.model_dump(exclude_none=True)


def _ranges(r):
    out = {}
    if r.pv_range:
        out["pv_range"] = tuple(r.pv_range)
    if r.mv_range:
        out["mv_range"] = tuple(r.mv_range)
    return out or None


def _protocol(res):
    checks = []
    for c in res["checks"]:
        checks.append(CheckItem(id=c["id"], name=i18n.T(f"ctl_chk_{c['id']}"), status=c["status"],
                                severity=c["severity"], message=i18n.T(c["msg"][0], **c["msg"][1]), rows=c.get("rows")))
    return CheckProtocol(verdict=res["verdict"], verdict_text=i18n.T(f"ctl_verdict_{res['verdict']}"), checks=checks,
                         reasons=res["reasons"])


def _http(ex):
    if isinstance(ex, KeyError):
        return HTTPException(404, "controller not found")
    if isinstance(ex, PermissionError):
        return HTTPException(403, "preset is read-only")
    raise ex


def router(lib: Library, writable=True):
    r = APIRouter(prefix="/controllers", tags=["controllers"])

    def get(pid):
        try:
            return lib.get(pid)
        except KeyError:
            raise HTTPException(404, "controller not found") from None

    def check_writable():
        if not writable:
            raise HTTPException(403, "library is read-only")

    @r.get("", response_model=list[ControllerSummary])
    def list_controllers():
        """Předvolby (jen ke čtení) a vlastní profily knihovny."""
        return lib.list()

    @r.get("/parts", response_model=list[PartInfo])
    def list_parts():
        """Katalog částí regulátoru (R3): popis a schéma parametrů každé položky registrů (pro skládání v editoru)."""
        return [PartInfo(kind=p["kind"], id=p["id"], description=i18n.T(p["desc_key"]), params=p["params"])
                for p in describe_parts()]

    @r.post("/compile", response_model=CompileResult, response_model_exclude_none=True)
    def compile_source(body: CompileRequest):
        """Překlad vlastních rovnic: chyby a varování s řádkem a sloupcem, při úspěchu program (strom výrazů), parametry
        a rychlé kontroly použitelnosti. Neukládá nic; uložení = import / PUT profilu s `kind = program`."""
        try:
            res = compile_program(body.source)
        except ProgramErrors as ex:
            return CompileResult(ok=False, errors=[_issue(e, "ctl_e") for e in ex.errors], warnings=[])
        prog = res["program"]
        data = dict(format=FORMAT, version=VERSION, id="draft", name="draft", kind="program", source=body.source)
        checks = None
        if body.quick:
            checks = _protocol(controller_check.run_check(
                data, only=["translation", "determinism", "rest", "direction", "switching", "numerics", "performance"]))
        full = make_profile(data).data
        return CompileResult(ok=True, errors=[], warnings=[_issue(w, "ctl_wn") for w in res["warnings"]], program=prog,
                             params=[ControllerParam(**p) for p in full["params"]], tuning_roles=tuning_roles(prog),
                             has_mapping=has_mapping(prog), checks=checks)

    @r.post("", response_model=ControllerProfile, status_code=201, response_model_exclude_none=True)
    def create_custom(body: NewController):
        """„Vytvořit vlastní“: kopie předvolby / vlastního profilu pod novým id."""
        check_writable()
        get(body.from_id)
        return lib.create_custom(body.from_id, body.name)

    @r.post("/import", response_model=ControllerProfile, status_code=201, response_model_exclude_none=True)
    def import_controller(body: ControllerProfile):
        """Import souboru `.pidctrl` (JSON); kolidující id dostane nové."""
        check_writable()
        data = _body(body)
        _compile(data)
        return lib.import_profile(data)

    @r.get("/{pid}", response_model=ControllerProfile, response_model_exclude_none=True)
    def get_controller(pid: str):
        return get(pid)

    @r.put("/{pid}", response_model=ControllerProfile, response_model_exclude_none=True)
    def update_controller(pid: str, body: ControllerProfile):
        """Změna vlastního profilu (id zůstává); předvolbu nelze měnit."""
        check_writable()
        data = _body(body)
        _compile(dict(data, id=pid))
        try:
            return lib.update(pid, data)
        except (KeyError, PermissionError) as ex:
            raise _http(ex) from None

    @r.delete("/{pid}", status_code=204)
    def delete_controller(pid: str):
        check_writable()
        try:
            lib.delete(pid)
        except (KeyError, PermissionError) as ex:
            raise _http(ex) from None

    @r.get("/{pid}/export", response_class=Response,
           responses={200: {"content": {"application/json": {}}, "description": "profile file (.pidctrl)"}})
    def export_controller(pid: str):
        get(pid)
        return Response(lib.export_profile(pid), media_type="application/json",
                       headers={"Content-Disposition": f'attachment; filename="{pid}.pidctrl"'})

    @r.post("/{pid}/test", response_model=CheckProtocol)
    def test_controller(pid: str):
        """Test použitelnosti (12 kontrol simulací) a hodnocení: Vhodný pro ladění / Jen optimalizací / Nevhodný."""
        return _protocol(controller_check.run_check(get(pid)))

    @r.post("/{pid}/map", response_model=MapResult)
    def map_canonical(pid: str, body: MapRequest):
        """Kanonický PID (Kc, Ti, Td, b, c, N) → hodnoty parametrů profilu v jeho jednotkách a varování."""
        prof = get(pid)
        c = body.canonical.model_dump()
        c["Ti"] = math.inf if c["Ti"] is None else c["Ti"]
        c["N"] = math.inf if c["N"] is None else c["N"]
        try:
            m = canonical_to_profile(prof, c, _ranges(body))
            eff = profile_to_canonical(prof, m["values"], _ranges(body))
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from ex
        return MapResult(values={k: _num(v) if isinstance(v, float) else v for k, v in m["values"].items()},
                         warnings=[Warning_(key=k, text=i18n.T(k, **a)) for k, a in m["warnings"]],
                         effective=_canon(eff))

    @r.post("/{pid}/canonical", response_model=CanonicalPID)
    def to_canonical(pid: str, body: CanonicalRequest):
        """Hodnoty parametrů profilu (např. sada 1 z PLC) → kanonický PID."""
        try:
            return _canon(profile_to_canonical(get(pid), body.values, _ranges(body)))
        except (ValueError, TypeError) as ex:
            raise HTTPException(422, str(ex)) from ex

    return r


def loop_router(project, lib: Library):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["controllers"])

    def view(ws):
        data = ws.controller or load_preset(DEFAULT_ID)
        return LoopController(profile=ControllerProfile(**data), is_default=ws.controller is None,
                              checksum=_checksum(data))

    @r.get("/controller", response_model=LoopController)
    def get_loop_controller(wid: str):
        """Profil regulátoru aktivní smyčky (kopie uložená v projektu); bez volby výchozí PIDConL."""
        return view(project(wid).state)

    @r.put("/controller", response_model=LoopController)
    def put_loop_controller(wid: str, body: LoopControllerPut):
        """Nastaví regulátor smyčky: kopie z knihovny (`from_id`), vlastní `profile`, nebo bez obojího výchozí PIDConL."""
        ws = project(wid).state
        if body.from_id and body.profile:
            raise HTTPException(422, "from_id and profile are mutually exclusive")
        if body.from_id:
            try:
                data = lib.get(body.from_id)
            except KeyError:
                raise HTTPException(404, "controller not found") from None
        elif body.profile:
            data = _body(body.profile)
            if not data.get("id"):
                raise HTTPException(422, "profile has no id")
            _compile(data)
        else:
            data = None
        ws.controller = None if data is None or data.get("id") == DEFAULT_ID and data == load_preset(DEFAULT_ID) else data
        return view(ws)

    return r

