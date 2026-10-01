/*
 * Automatické ukládání projektu do prohlížeče (IndexedDB – zůstává jen v tomto počítači, nikam se neposílá).
 * data.mode: "probe" = zjistit, zda je uložená práce (trigger „found“ s popisem nebo {}),
 *            "save"  = uložit data.json (jen když se změnil), "load" = poslat uložený projekt (trigger „project“),
 *            "clear" = smazat uložené, "idle" = nic.
 */
export default function (component) {
  const { data, setTriggerValue } = component;
  const DB = "pidtools", STORE = "autosave", KEY = "last";
  function db() {
    return new Promise((ok, err) => {
      const r = indexedDB.open(DB, 1);
      r.onupgradeneeded = () => r.result.createObjectStore(STORE);
      r.onsuccess = () => ok(r.result);
      r.onerror = () => err(r.error);
    });
  }
  function tx(mode, fn) {
    return db().then((d) => new Promise((ok, err) => {
      const t = d.transaction(STORE, mode), s = t.objectStore(STORE), req = fn(s);
      t.oncomplete = () => ok(req && req.result);
      t.onerror = () => err(t.error);
    }));
  }
  const mode = data && data.mode;
  window.__pidAutosave = window.__pidAutosave || {};
  if (mode === "save" && data.json && window.__pidAutosave.lastHash !== data.hash) {
    window.__pidAutosave.lastHash = data.hash;
    tx("readwrite", (s) => s.put({ saved_at: data.saved_at, meta: data.meta, json: data.json }, KEY))
      .catch((e) => console.warn("PID Tools autosave:", e));
  } else if (mode === "probe") {
    tx("readonly", (s) => s.get(KEY))
      .then((v) => setTriggerValue("found", v ? Object.assign({ saved_at: v.saved_at }, v.meta || {}) : {}))
      .catch(() => setTriggerValue("found", {}));
  } else if (mode === "load") {
    tx("readonly", (s) => s.get(KEY)).then((v) => { if (v) setTriggerValue("project", v.json); });
  } else if (mode === "clear") {
    window.__pidAutosave.lastHash = null;
    tx("readwrite", (s) => s.delete(KEY)).then(() => setTriggerValue("found", {}));
  }
}
