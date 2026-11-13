// Režim nasazení ze serveru (`/config`): ve veřejném režimu (bez přihlášení, nic se neukládá na server) se vypínají
// OPC UA, historiany, logo, záchranná kopie a přílohy deníku a zobrazuje se upozornění na soukromí.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import { useT } from "./i18n";

export const useConfig = () => useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity, retry: 2 });

export const usePublic = () => useConfig().data?.mode === "public";

/** Upozornění na soukromí ve veřejném režimu; mimo něj nic. `short` = jedna věta (Start), jinak s nadpisem (nápověda). */
export function PublicNotice({ short = false }: { short?: boolean }) {
  const T = useT();
  const cfg = useConfig().data;
  if (cfg?.mode !== "public") return null;
  const min = Math.round(cfg.session_ttl_min ?? 120);
  return short
    ? <p className="rg-note pub-notice" data-testid="public-notice">{T("pub_notice_short")}</p>
    : <section className="pub-notice" data-testid="public-notice-help"><h3>{T("pub_notice_title")}</h3><p>{T("pub_notice", { min })}</p></section>;
}
