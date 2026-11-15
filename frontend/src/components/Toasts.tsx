// Jednotné hlášení: úložiště oznámení (Zustand) a oblast vpravo dole (role="status", aria-live="polite").
// Chyba zůstává do zavření, „ok“ zmizí po 4 s; nejvýš 4 najednou; text, který už je vidět, se nepřidává znovu.
import { create } from "zustand";
import { ApiError } from "../api/client";
import { useT } from "../i18n";

export type ToastKind = "err" | "ok";
export interface Toast { id: number; kind: ToastKind; text: string }

export const MAX_TOASTS = 4;
export const OK_MS = 4000;

interface ToastStore {
  items: Toast[];
  push: (t: { kind: ToastKind; text: string }) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useToasts = create<ToastStore>((set, get) => ({
  items: [],
  push: ({ kind, text }) => {
    if (get().items.some((x) => x.text === text)) return;          // stejný text už je zobrazený
    const id = nextId++;
    set((s) => ({ items: [...s.items, { id, kind, text }].slice(-MAX_TOASTS) }));
    if (kind === "ok") setTimeout(() => get().dismiss(id), OK_MS);
  },
  dismiss: (id) => set((s) => ({ items: s.items.filter((x) => x.id !== id) })),
}));

/** Chybový toast z libovolné výjimky (u ApiError je to text serveru). */
export function toastError(e: unknown): void {
  const text = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
  useToasts.getState().push({ kind: "err", text });
}

export function Toasts() {
  const T = useT();
  const items = useToasts((s) => s.items);
  const dismiss = useToasts((s) => s.dismiss);
  return (
    <div className="toasts" role="status" aria-live="polite" data-testid="toasts">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`} data-testid={`toast-${t.kind}`}>
          <span className="toast-text">{t.text}</span>
          <button type="button" className="toast-x" aria-label={T("toast_close")} data-testid="toast-close"
            onClick={() => dismiss(t.id)}>×</button>
        </div>
      ))}
    </div>
  );
}
