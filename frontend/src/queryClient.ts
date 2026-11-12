// Jediná instance TanStack Query (aby k ní měly přístup i moduly mimo komponenty, např. úložiště Nastavení).
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });
