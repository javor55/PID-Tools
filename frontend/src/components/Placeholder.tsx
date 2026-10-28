import { useT } from "../i18n";

export function Placeholder({ milestone }: { milestone: string }) {
  const T = useT();
  return <div className="card muted">{T("ui_soon", { m: milestone })}</div>;
}
