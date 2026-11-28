// Jednotné vykreslení stavu dotazu: načítání (kostra), chyba (+ Zkusit znovu), prázdno (+ odkaz na chybějící krok), data.
import type { ReactNode } from "react";
import { ApiError } from "../api/client";
import { useT } from "../i18n";
import "../styles/state.css";

/** Ze `useQuery` stačí tato pole. */
export interface QueryLike<T> {
  data: T | undefined; isPending: boolean; isError: boolean; error: Error | null; isFetching: boolean;
  refetch: () => unknown;
}

export function QueryState<T>({ q, empty, emptyText, action, children }: {
  q: QueryLike<T>; empty?: (data: T) => boolean; emptyText?: string;
  action?: { label: string; onClick: () => void }; children: (data: T) => ReactNode;
}) {
  const T_ = useT();
  const emptyBox = (text: string) => (
    <div className="qs-msg" data-testid="qs-empty"><span>{text}</span>
      {action && <button type="button" data-testid="qs-action" onClick={action.onClick}>{action.label}</button>}</div>);
  if (q.data === undefined) {
    if (q.isError) {
      if (q.error instanceof ApiError && q.error.status === 409) return emptyBox(T_("need_model"));
      return (
        <div className="qs-msg qs-err" data-testid="qs-error"><span>{q.error?.message}</span>
          <button type="button" data-testid="qs-retry" onClick={() => { void q.refetch(); }}>{T_("qs_retry")}</button></div>);
    }
    return (
      <div className="qs-skeleton" role="status" aria-live="polite" data-testid="qs-skeleton">
        <span className="qs-vh">{T_("qs_loading")}</span><i /><i /><i /></div>);
  }
  if (empty?.(q.data)) return emptyBox(emptyText ?? "");
  return (
    <div className={q.isFetching ? "is-busy" : undefined} aria-busy={q.isFetching ? "true" : undefined}>
      {children(q.data)}</div>);
}
