// Jediná instance TanStack Query (aby k ní měly přístup i moduly mimo komponenty, např. úložiště Nastavení).
// Neúspěšné dotazy a změny se hlásí jednotně toastem; výjimky z pravidla jsou popsané u `shouldToast`.
import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "./api/client";
import { toastError } from "./components/Toasts";
import { useUi } from "./store";

const isAbort = (e: unknown) => e instanceof DOMException && e.name === "AbortError";

/**
 * Kdy se toast NEukáže: zrušený požadavek; 404 (ztracený prostor – řeší obnova prostoru) a 409 (chybí model – řeší
 * prázdné stavy pohledů); 422 u dotazů (pohledy ho berou jako „nelze spočítat“ a ukazují si ho samy).
 */
export function shouldToast(e: unknown, isQuery: boolean): boolean {
  if (isAbort(e)) return false;
  if (e instanceof ApiError) {
    if (e.status === 404 || e.status === 409) return false;
    if (isQuery && e.status === 422) return false;
  }
  return true;
}

// Obsluha ztráty prostoru se registruje z workspace.ts (přímý import by udělal cyklus queryClient ↔ workspace).
let onLost: () => void = () => undefined;
export const setWorkspaceLostHandler = (fn: () => void) => { onLost = fn; };

/** Server hlásí, že prostor neexistuje (přesný text `project()` v API). */
const isLost = (e: unknown) => e instanceof ApiError && e.status === 404 && e.message === "workspace not found";

// Dotazy, jejichž selhání zobrazuje stavový řádek / úvodní obrazovka sama.
const SELF_REPORTED = new Set(["health", "config"]);

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (e, q) => {
      // Jen dotaz aktuálního prostoru (pozdní odpověď staršího prostoru nic nespouští).
      if (isLost(e) && q.queryKey[0] === "ws" && q.queryKey[1] === useUi.getState().wid) onLost();
      if (!SELF_REPORTED.has(String(q.queryKey[0])) && shouldToast(e, true)) toastError(e);
    },
  }),
  mutationCache: new MutationCache({
    onError: (e) => { if (isLost(e)) onLost(); if (shouldToast(e, false)) toastError(e); },
  }),
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

/** Nezachycené odmítnutí s ApiError (`void patch(...)` apod.): toast a ticho v konzoli. */
export function onUnhandledRejection(ev: PromiseRejectionEvent): void {
  const e = ev.reason;
  if (e instanceof ApiError && shouldToast(e, false)) { toastError(e); ev.preventDefault(); }
  else if (e instanceof ApiError) ev.preventDefault();             // 404 / 409 řeší jiná část rozhraní
}

window.addEventListener("unhandledrejection", onUnhandledRejection);
