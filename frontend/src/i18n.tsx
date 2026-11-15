// Texty z API (/i18n/{lang} – stejné soubory jako Python). T(klíč, argumenty) jako v Pythonu.
import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, type Language } from "./api/client";
import { format } from "./lib/format";
import { useUi } from "./store";

export function useTexts() {
  const lang = useUi((s) => s.lang);
  return useQuery({ queryKey: ["i18n", lang], queryFn: () => api.texts(lang), staleTime: Infinity }).data;
}

export type { Language };

/** Dostupné jazyky (soubory pidtools/i18n/*.json), angličtina první. */
export function useLanguages(): Language[] {
  return useQuery({ queryKey: ["i18n-langs"], queryFn: api.languages, staleTime: Infinity }).data
    ?? [{ code: "en", name: "English", coverage: 1 }];
}

/** Desetinný oddělovač jazyka: klíč `_decimal` jazykového souboru, jinak podle Intl (stejně jako Python i18n.decimal). */
export const decOf = (lang: string, texts?: Record<string, string>) =>
  texts?._decimal ?? (() => { try { return (1.5).toLocaleString(lang).charAt(1) || "."; } catch { return "."; } })();

export function useDec(): string {
  const lang = useUi((s) => s.lang);
  return decOf(lang, useTexts());
}

/** Locale pro datum a čas: angličtina s 24h časem (en-GB), jinak kód jazyka. */
export const dateLocale = (lang: string) => (lang === "en" ? "en-GB" : lang);

export function useT() {
  const data = useTexts();
  return useCallback(
    (key: string, args?: Record<string, unknown>) => format(data?.[key] ?? key, args),
    [data],
  );
}
