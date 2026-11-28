// Hranice chyb kolem obsahu záložky: výjimka při vykreslení nezruší celé okno, hlavička a stavový řádek zůstanou.
import { Component, type ReactNode } from "react";
import { request } from "../api/client";
import type { Config } from "../api/client";
import { useT } from "../i18n";
import { queryClient } from "../queryClient";
import { useUi } from "../store";
import { toastError, useToasts } from "./Toasts";

/** Záchranná kopie z karty chyby: bez wid a ve veřejném režimu (server nic neukládá) se tlačítko nenabízí. */
function canSaveRecovery(): boolean {
  const cfg = queryClient.getQueryData<Config>(["config"]);
  return !!useUi.getState().wid && cfg?.mode !== "public";
}

function Fallback({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const T = useT();
  const save = () => {
    const wid = useUi.getState().wid;
    if (!wid) return;
    request("POST", `/workspaces/${wid}/autosave`)
      .then(() => useToasts.getState().push({ kind: "ok", text: T("err_boundary_saved") }))
      .catch(toastError);
  };
  return (
    <div className="card err-boundary" role="alert" data-testid="err-boundary">
      <h2 className="err-boundary-title">{T("err_boundary_title")}</h2>
      <p className="err-boundary-msg" data-testid="err-boundary-msg">{error.message}</p>
      <button type="button" data-testid="err-boundary-retry" onClick={onRetry}>{T("err_boundary_retry")}</button>
      {canSaveRecovery() && (
        <button type="button" data-testid="err-save-recovery" onClick={save}>{T("err_boundary_save_recovery")}</button>
      )}
    </div>
  );
}

interface Props { children: ReactNode; resetKey?: string }
interface State { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State { return { error }; }

  componentDidCatch(error: Error) { console.error("ErrorBoundary:", error); }

  componentDidUpdate(prev: Props) {
    // Přepnutí záložky / podzáložky chybu smaže.
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (this.state.error) return <Fallback error={this.state.error} onRetry={() => this.setState({ error: null })} />;
    return this.props.children;
  }
}
