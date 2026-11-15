// Hranice chyb kolem obsahu záložky: výjimka při vykreslení nezruší celé okno, hlavička a stavový řádek zůstanou.
import { Component, type ReactNode } from "react";
import { useT } from "../i18n";

function Fallback({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const T = useT();
  return (
    <div className="card err-boundary" role="alert" data-testid="err-boundary">
      <h2 className="err-boundary-title">{T("err_boundary_title")}</h2>
      <p className="err-boundary-msg" data-testid="err-boundary-msg">{error.message}</p>
      <button type="button" data-testid="err-boundary-retry" onClick={onRetry}>{T("err_boundary_retry")}</button>
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
