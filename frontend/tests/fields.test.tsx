// NumSetting: místní kontrola mezí (bez PATCH), chyba u pole (aria-invalid + popis), Esc, chyba 422 ze serveru.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import en from "../../pidtools/i18n/en.json";
import { NumSetting } from "../src/components/Fields";
import { format } from "../src/lib/format";
import { useUi } from "../src/store";

// texty dodává server; v testu se berou z en.json
vi.mock("../src/i18n", () => ({
  useT: () => (k: string, a?: Record<string, unknown>) => format((en as Record<string, string>)[k] ?? k, a),
}));

const WID = "w1";
let calls: { method: string; body: unknown }[] = [];
let patchReply: () => Response;

function setup(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  qc.setQueryData(["ws", WID, "settings"], { samp: 1, other: 7 });
  useUi.setState({ wid: WID });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}
const field = () => screen.getByTestId("set-samp") as HTMLInputElement;
const type = (v: string) => { fireEvent.focus(field()); fireEvent.change(field(), { target: { value: v } }); fireEvent.blur(field()); };
const patches = () => calls.filter((c) => c.method === "PATCH");

beforeEach(() => {
  calls = [];
  patchReply = () => new Response(JSON.stringify({ samp: 5, other: 7 }), { status: 200, headers: { "Content-Type": "application/json" } });
  vi.stubGlobal("fetch", vi.fn(async (_u: string, init?: RequestInit) => {
    calls.push({ method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return init?.method === "PATCH" ? patchReply() : new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("NumSetting", () => {
  it("-1 with min=0: no PATCH, aria-invalid, error text stays; a valid value sends and clears the error", async () => {
    setup(<NumSetting k="samp" label="Sample" min={0} />);
    type("-1");
    expect(field().getAttribute("aria-invalid")).toBe("true");
    expect(field().value).toBe("-1");
    const err = screen.getByTestId("set-samp-err");
    expect(err.textContent).toBe("Must be at least 0");
    expect(field().getAttribute("aria-describedby")).toBe(err.id);
    expect(patches()).toHaveLength(0);
    type("5");
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(patches()[0].body).toEqual({ samp: 5 });
    await waitFor(() => expect(screen.queryByTestId("set-samp-err")).toBeNull());
    expect(field().getAttribute("aria-invalid")).toBeNull();
  });

  it("empty / non-numeric text shows 'Enter a number' and sends nothing", () => {
    setup(<NumSetting k="samp" label="Sample" />);
    type("abc");   // číselné pole v prohlížeči i v jsdom vrací u textu prázdný řetězec
    expect(screen.getByTestId("set-samp-err").textContent).toBe("Enter a number");
    expect(patches()).toHaveLength(0);
  });

  it("minExclusive, max and integer have their own messages", () => {
    setup(<NumSetting k="samp" label="Sample" min={0} minExclusive max={10} integer />);
    type("0"); expect(screen.getByTestId("set-samp-err").textContent).toBe("Must be greater than 0");
    type("11"); expect(screen.getByTestId("set-samp-err").textContent).toBe("Must be at most 10");
    type("2.5"); expect(screen.getByTestId("set-samp-err").textContent).toBe("Must be a whole number");
    expect(patches()).toHaveLength(0);
  });

  it("Esc restores the original value and clears the error", () => {
    setup(<NumSetting k="samp" label="Sample" min={0} />);
    type("-1");
    expect(field().getAttribute("aria-invalid")).toBe("true");
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(field().value).toBe("1");
    expect(screen.queryByTestId("set-samp-err")).toBeNull();
    expect(field().getAttribute("aria-invalid")).toBeNull();
  });

  it("a 422 from the server shows its text at the field and keeps the typed text", async () => {
    patchReply = () => new Response(JSON.stringify({ detail: "samp: must be > 0" }), { status: 422, headers: { "Content-Type": "application/json" } });
    setup(<NumSetting k="samp" label="Sample" />);
    type("3");
    await waitFor(() => expect(screen.getByTestId("set-samp-err").textContent).toContain("samp: must be > 0"));
    expect(patches()).toHaveLength(1);
    expect(field().value).toBe("3");
    expect(field().getAttribute("aria-invalid")).toBe("true");
  });
});
