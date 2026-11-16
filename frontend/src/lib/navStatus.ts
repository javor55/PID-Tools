// Značka a souhrn stavu postupu záložky (FEATURE-003) – čistá funkce nad odpovědí GET /guide/status.
import type { components } from "../api/schema";

export type TabStatus = components["schemas"]["TabStatus"];
export type NavMark = "ok" | "warn" | null;

/** `ok` (✓) = nic k doplnění a aspoň jedna splněná položka; `warn` (!) = aspoň jedno varování; jinak bez značky. */
export function navMark(s: TabStatus | undefined): NavMark {
  if (!s) return null;
  if (s.warn > 0) return "warn";
  return s.todo === 0 && s.ok > 0 ? "ok" : null;
}
