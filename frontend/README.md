# PID Tools – nové rozhraní (React + TypeScript)

Jedno rozhraní pro web i offline desktop nad Python API (`pidtools.api`). Plán a stav: `docs/cs/milniky.md` (M12–M21).

```bash
cd frontend
npx -y npm@11.21.0 ci              # závislosti (npm 11 – npm 10 padá na peer závislostech vitestu)
python -m pidtools.api --port 8765 --token dev   # v jiném terminálu (z kořene repozitáře)
npm run dev                         # http://localhost:5173/#token=dev  (Vite přeposílá API na :8765)
npm run lint && npm run typecheck && npm test
npm run build                       # → pidtools/api/ui; API ho pak servíruje na /
npm run api-types                   # po změně API: typy z pidtools/api/openapi.json
```

- `src/api` – klient API a generované typy (`schema.d.ts`, needitovat).
- `src/store.ts` – stav rozhraní (Zustand). Výsledky výpočtů drží TanStack Query.
- `src/lib/format.ts` – texty s formátem jako Python (`{x:.4g}`).
- `src/styles` – design tokeny (barvy, fonty) shodné s dnešním webem.
- Nápověda: každé pole s popiskem má „?“ (`LabelHelp` v `components/Ui.tsx`; `NumSetting` / `SelectSetting` /
  `CheckSetting` / `TextSetting` berou `help` = klíč překladu nebo text, `Seg` také). Nové pole bez nápovědy
  neprojde testem `tests/test_frontend_help.py` (Playwright prochází všechny záložky a struktury APC). Průvodce
  záložky (F1, `components/Guide.tsx`) čte `GET /workspaces/{wid}/guide/{tab}`; obsah a kontrolní seznam jsou v
  `pidtools/app/guides.py`.
- Verze balíčků jsou přesně zafixované a vybrané tak, aby byly staré aspoň dva týdny.
