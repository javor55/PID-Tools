// Texty z API (/i18n/{lang} – stejné soubory jako Python). T(klíč, argumenty) jako v Pythonu.
import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { api } from "./api/client";
import { format } from "./lib/format";
import { useUi } from "./store";

export function useT() {
  const lang = useUi((s) => s.lang);
  const { data } = useQuery({ queryKey: ["i18n", lang], queryFn: () => api.texts(lang), staleTime: Infinity });
  return useCallback(
    (key: string, args?: Record<string, unknown>) => format(data?.[key] ?? key, args),
    [data],
  );
}
