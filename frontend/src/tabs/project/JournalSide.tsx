// Pravý panel Deníku ladění: „Uložit verzi“ (neměnný snímek aktivní smyčky s názvem a poznámkou).
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "../../api/client";
import { PrimaryAction, SideCard } from "../../components/Ui";
import { useT } from "../../i18n";
import { useUi } from "../../store";
import { useErr } from "./JournalMain";
import { type SnapshotDetail, useProjSub } from "./state";

export function JournalSide() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const select = useProjSub((s) => s.select);
  const { err, run } = useErr();
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const save = () => run(async () => {
    const d = await request<SnapshotDetail>("POST", `/workspaces/${wid}/journal`, { label, note });
    setLabel(""); setNote("");
    setMsg(T("jr_saved").replace("{name}", `${d.loop} v${d.v}`));
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
    select(d.id);
  });
  return (
    <>
      <PrimaryAction onClick={() => void save()} testid="jr-save" title={T("h_jr_save")}>{T("jr_save")}</PrimaryAction>
      <SideCard title={T("jr_new")} help={T("h_jr_new")} testid="jr-new">
        <label className="field"><span className="lbl">{T("jr_label")}</span>
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={T("jr_label_ph")} title={T("h_jr_label")} data-testid="jr-label" /></label>
        <label className="field"><span className="lbl">{T("jr_note")}</span>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} title={T("h_jr_note")} data-testid="jr-note-new" /></label>
        {msg && <div className="ok small" role="status" data-testid="jr-saved">{msg}</div>}
        {err && <div className="err small" role="alert">{err}</div>}
      </SideCard>
    </>
  );
}
