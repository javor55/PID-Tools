"""
Čtení dat z OPC UA serveru (SIMATIC PCS 7 OS / Process Historian, WinCC, jiné DCS) – **jen čtení**: procházení
adresního prostoru, aktuální hodnoty, historie (HistoryRead) a záznam živých hodnot. Nic se do serveru nezapisuje.

Výsledek je tabulka v dlouhém formátu (Tag, Time, Value), kterou aplikace načte stejně jako export z historianu.
Názvy tagů = cesta v adresním prostoru („FIC101.PV“), aby fungoval odhad rolí PV / MV / SP.
Volitelná závislost: asyncua (pip install asyncua); bez ní je funkce nedostupná, zbytek aplikace běží.
"""
import datetime as dt
import time
from dataclasses import dataclass

import pandas as pd


def available():
    """Je knihovna asyncua nainstalovaná?"""
    try:
        import asyncua  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class Item:
    """Uzel adresního prostoru: id, zobrazované jméno, cesta (tag), proměnná ano/ne."""
    node_id: str
    name: str
    path: str
    is_var: bool


def _utc(t):
    if t is None:
        return None
    return t.replace(tzinfo=dt.timezone.utc) if t.tzinfo is None else t.astimezone(dt.timezone.utc)


class Connection:
    """Připojení k OPC UA serveru (synchronní klient asyncua). Použití: with Connection(url) as c: …"""

    def __init__(self, url, user=None, password=None, timeout=10.0, security=None):
        from asyncua.sync import Client
        self.url = url
        self.client = Client(url, timeout=timeout)
        if user:
            self.client.set_user(user)
            self.client.set_password(password or "")
        if security:                      # např. "Basic256Sha256,SignAndEncrypt,cert.pem,key.pem"
            self.client.set_security_string(security)
        self._paths = {}

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    def connect(self):
        self.client.connect()

    def close(self):
        try:
            self.client.disconnect()
        except Exception:
            pass

    # ---- adresní prostor
    def node(self, node_id):
        return self.client.get_node(node_id)

    def children(self, node_id=None, parent_path=""):
        """Podřízené uzly (výchozí: složka Objects) – bez standardní složky Server."""
        from asyncua import ua
        base = self.client.nodes.objects if node_id is None else self.node(node_id)
        out = []
        for ch in base.get_children(refs=ua.ObjectIds.HierarchicalReferences):
            try:
                name = ch.read_browse_name().Name
                cls = ch.read_node_class()
            except Exception:
                continue
            if node_id is None and name in ("Server", "Aliases", "Locations"):
                continue
            path = f"{parent_path}.{name}" if parent_path else name
            nid = ch.nodeid.to_string()
            is_var = cls == ua.NodeClass.Variable
            if is_var:
                self._paths[nid] = path
            out.append(Item(nid, name, path, is_var))
        return out

    def find(self, text, node_id=None, depth=6, limit=300):
        """Proměnné, jejichž cesta obsahuje text (bez rozlišení velikosti písmen) – prohledání do hloubky depth."""
        text = (text or "").lower()
        out, stack = [], [(node_id, "", 0)]
        while stack and len(out) < limit:
            nid, path, d = stack.pop()
            for it in self.children(nid, path):
                if it.is_var and text in it.path.lower():
                    out.append(it)
                if not it.is_var and d + 1 < depth:
                    stack.append((it.node_id, it.path, d + 1))
        return out

    def path(self, node_id):
        """Cesta uzlu (z procházení), jinak jeho zobrazované jméno."""
        if node_id in self._paths:
            return self._paths[node_id]
        try:
            return self.node(node_id).read_browse_name().Name
        except Exception:
            return node_id

    # ---- hodnoty
    def read(self, node_ids):
        """Aktuální hodnoty {node_id: hodnota}."""
        return {n: self.node(n).read_value() for n in node_ids}

    def history(self, node_ids, start, end, progress=None):
        """
        Historie (HistoryRead, raw) pro uzly v intervalu [start, end] (datetime, bez zóny = UTC).
        Vrací {node_id: (časy UTC, hodnoty)}; uzel bez historie → prázdné pole.
        """
        out = {}
        for i, n in enumerate(node_ids):
            if progress:
                progress(i, self.path(n))
            try:
                h = self.node(n).read_raw_history(_utc(start), _utc(end))
            except Exception:
                h = []
            pts = sorted(((_utc(v.SourceTimestamp or v.ServerTimestamp), v.Value.Value) for v in h
                          if v.Value is not None and v.Value.Value is not None), key=lambda x: x[0])
            out[n] = ([p[0] for p in pts], [p[1] for p in pts])
        return out

    def record(self, node_ids, period, duration, progress=None, stop=None):
        """Záznam živých hodnot: čtení každých period s po dobu duration s. {node_id: (časy UTC, hodnoty)}."""
        out = {n: ([], []) for n in node_ids}
        t_end = time.monotonic() + duration
        k = 0
        while time.monotonic() < t_end and not (stop and stop()):
            now = dt.datetime.now(dt.timezone.utc)
            vals = self.client.read_values([self.node(n) for n in node_ids])
            for n, v in zip(node_ids, vals):
                out[n][0].append(now)
                out[n][1].append(v)
            k += 1
            if progress:
                progress(min(1.0, 1 - (t_end - time.monotonic()) / duration), k)
            time.sleep(max(0.0, period - 0.002))
        return out


def to_frame(series, names):
    """
    {node_id: (časy, hodnoty)} → dlouhá tabulka Tag, Time (místní čas, text ISO), Value. names = {node_id: tag}.
    Nečíselné hodnoty (text, stav) se vynechají.
    """
    rows = []
    for n, (ts, vs) in series.items():
        tag = names.get(n, n)
        for t, v in zip(ts, vs):
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            rows.append((tag, pd.Timestamp(t).tz_convert(None) if pd.Timestamp(t).tzinfo else pd.Timestamp(t), x))
    df = pd.DataFrame(rows, columns=["Tag", "Time", "Value"])
    if len(df):
        loc = dt.datetime.now().astimezone().utcoffset() or dt.timedelta(0)
        df["Time"] = (df["Time"] + loc).dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
        df = df.sort_values(["Time", "Tag"]).reset_index(drop=True)
    return df


def test_server(port=48420, n=600, step=1.0, seed=1):
    """
    Lokální testovací OPC UA server s historií (dvě smyčky FIC101, TIC200 se skoky MV) – pro testy a ukázku.
    Vrací (url, stop): stop() server ukončí. Běží ve vlákně.
    """
    import asyncio
    import threading

    import numpy as np
    from asyncua import Server, ua

    ready, stopper = threading.Event(), threading.Event()
    url = f"opc.tcp://127.0.0.1:{port}/pidtools/"

    async def main():
        srv = Server()
        await srv.init()
        srv.set_endpoint(url)
        idx = await srv.register_namespace("urn:pidtools:test")
        t0 = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=n * step)
        rng = np.random.default_rng(seed)
        nodes = {}
        for tag in ("FIC101", "TIC200"):
            obj = await srv.nodes.objects.add_object(idx, tag)
            for sig in ("PV", "MV", "SP"):
                nodes[(tag, sig)] = await obj.add_variable(idx, sig, 50.0, varianttype=ua.VariantType.Double)
        async with srv:
            hm = srv.iserver.history_manager
            for node in nodes.values():
                await hm.historize_data_change(node, period=None, count=n + 10)
            pv = {"FIC101": 50.0, "TIC200": 60.0}
            for k in range(n):
                ts = t0 + dt.timedelta(seconds=k * step)
                for tag, (K, T) in (("FIC101", (1.2, 15.0)), ("TIC200", (0.8, 60.0))):
                    mv = 50.0 + (8.0 if (k // 120) % 2 else 0.0)
                    pv[tag] += step / T * (K * (mv - 50.0) + 50.0 - pv[tag])
                    for sig, v in (("PV", pv[tag] + rng.normal(0, 0.05)), ("MV", mv), ("SP", 50.0)):
                        dv = ua.DataValue(ua.Variant(float(v), ua.VariantType.Double), SourceTimestamp=ts,
                                          ServerTimestamp=ts)
                        await hm.storage.save_node_value(nodes[(tag, sig)].nodeid, dv)
            ready.set()
            while not stopper.is_set():
                await asyncio.sleep(0.05)

    th = threading.Thread(target=lambda: asyncio.run(main()), daemon=True)
    th.start()
    if not ready.wait(30):
        raise RuntimeError("OPC UA test server did not start")
    return url, stopper.set
