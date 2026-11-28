// Líné načítání těžkých záložek (TICKET-019): každý modul je samostatný chunk, který se stáhne až při prvním zobrazení.
// Pojmenované exporty se převádějí na výchozí. Náhradní obsah = kostra jako při načítání dotazu (QueryState).
import { type ComponentType, lazy, type LazyExoticComponent, Suspense, type ReactNode } from "react";
import { useT } from "./i18n";
import "./styles/state.css";

/**
 * `React.lazy` pro pojmenovaný export. Selhání načtení chunku (např. desktop po aktualizaci) `lazy` zapamatuje
 * navždy, proto se po chybě vytvoří nová instance: „Try again“ v ErrorBoundary pak načtení zopakuje.
 */
function lazyNamed<M, K extends keyof M>(
  load: () => Promise<M>, name: K,
): M[K] extends ComponentType<infer P> ? ComponentType<P> : never {
  type P = M[K] extends ComponentType<infer Q> ? Q : never;
  const make = (): LazyExoticComponent<ComponentType<P>> =>
    lazy(() => load().then((m) => ({ default: m[name] as ComponentType<P> })).catch((e: unknown) => { cur = make(); throw e; }));
  let cur = make();
  const LazyTab = (props: P) => {
    const C = cur;
    return <C {...(props as P & object)} />;
  };
  return LazyTab as ReturnType<typeof lazyNamed<M, K>>;
}

export const ModelMain = lazyNamed(() => import("./tabs/ModelTab"), "ModelMain");
export const ModelSide = lazyNamed(() => import("./tabs/ModelTab"), "ModelSide");
export const TuningMain = lazyNamed(() => import("./tabs/TuningTab"), "TuningMain");
export const TuningSide = lazyNamed(() => import("./tabs/TuningTab"), "TuningSide");
export const DiagMain = lazyNamed(() => import("./tabs/DiagTab"), "DiagMain");
export const DiagSide = lazyNamed(() => import("./tabs/DiagTab"), "DiagSide");
export const TriageMain = lazyNamed(() => import("./tabs/TriageTab"), "TriageMain");
export const TriageSide = lazyNamed(() => import("./tabs/TriageTab"), "TriageSide");
export const SettingsPage = lazyNamed(() => import("./settings/SettingsPage"), "SettingsPage");
export const ApcMain = lazyNamed(() => import("./tabs/ApcTab"), "ApcMain");
export const ApcSide = lazyNamed(() => import("./tabs/ApcTab"), "ApcSide");
export const LiveMain = lazyNamed(() => import("./tabs/LiveTab"), "LiveMain");
export const TrendsMain = lazyNamed(() => import("./tabs/data/TrendsView"), "TrendsMain");
export const TrendsSide = lazyNamed(() => import("./tabs/data/TrendsView"), "TrendsSide");
export const ProjectMain = lazyNamed(() => import("./tabs/ProjectTab"), "ProjectMain");
export const ProjectSide = lazyNamed(() => import("./tabs/ProjectTab"), "ProjectSide");

/** Kostra stejného vzhledu jako `QueryState` při načítání. */
export function LoadingSkeleton() {
  const T = useT();
  return (
    <div className="qs-skeleton" role="status" aria-live="polite" data-testid="qs-skeleton">
      <span className="qs-vh">{T("qs_loading")}</span><i /><i /><i /></div>);
}

/**
 * Hranice `Suspense` s kostrou. Každé místo použití má v App vlastní `key` (záložka + podzáložka): při přepnutí se
 * stará záložka odmontuje hned, React ji jinak jen skryje (`display: none`) a ponechá v DOM do načtení chunku.
 */
export function Lazy({ children }: { children: ReactNode }) {
  return <Suspense fallback={<LoadingSkeleton />}>{children}</Suspense>;
}
