// Texty z API (/i18n/{lang} – stejné soubory jako Python). T(klíč, argumenty) jako v Pythonu.
import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { api } from "./api/client";
import { format } from "./lib/format";
import { useUi } from "./store";

export function useTexts() {
  const lang = useUi((s) => s.lang);
  return useQuery({ queryKey: ["i18n", lang], queryFn: () => api.texts(lang), staleTime: Infinity }).data;
}

export function useT() {
  const data = useTexts();
  return useCallback(
    (key: string, args?: Record<string, unknown>) => format(data?.[key] ?? key, args),
    [data],
  );
}
