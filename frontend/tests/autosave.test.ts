// Záchranná kopie při zavření okna: rozhodnutí `shouldFlush`, `postKeepalive` a tlačítko v kartě chyby.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SaveState } from "../src/start/project";

const state = (o: Partial<SaveState> = {}): SaveState =>
  ({ has_data: true, dirty: true, rev: 5, autosave_pending: true, ...o }) as SaveState;
const ok = { public: false, minutes: 1, lastFlushedRev: -1 };

describe("shouldFlush", () => {
  it("odešle při čekající změně", async () => {
    const { shouldFlush } = await import("../src/start/project");
    expect(shouldFlush(state(), ok)).toBe(true);
  });
  it("neodešle bez dat, bez čekající změny, bez stavu", async () => {
    const { shouldFlush } = await import("../src/start/project");
    expect(shouldFlush(state({ has_data: false }), ok)).toBe(false);
    expect(shouldFlush(state({ autosave_pending: false }), ok)).toBe(false);
    expect(shouldFlush(undefined, ok)).toBe(false);
  });
  it("neodešle ve veřejném režimu ani při vypnutém ukládání", async () => {
    const { shouldFlush } = await import("../src/start/project");
    expect(shouldFlush(state(), { ...ok, public: true })).toBe(false);
    expect(shouldFlush(state(), { ...ok, minutes: 0 })).toBe(false);
  });
  it("pro stejný rev podruhé neodešle", async () => {
    const { shouldFlush } = await import("../src/start/project");
    expect(shouldFlush(state({ rev: 7 }), { ...ok, lastFlushedRev: 7 })).toBe(false);
    expect(shouldFlush(state({ rev: 8 }), { ...ok, lastFlushedRev: 7 })).toBe(true);
  });
});

describe("postKeepalive", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("pošle POST s keepalive a tokenem, bez čekání na relaci", async () => {
    vi.resetModules();
    const f = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", f);
    const c = await import("../src/api/client");
    c.setToken("tok");
    c.postKeepalive("/workspaces/w1/autosave");
    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/workspaces/w1/autosave");
    expect(init.method).toBe("POST");
    expect(init.keepalive).toBe(true);
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });
  it("odmítnutý fetch tiše ignoruje", async () => {
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("síť"); }));
    const c = await import("../src/api/client");
    expect(() => c.postKeepalive("/x")).not.toThrow();
    await new Promise((r) => setTimeout(r, 0));
  });
});

describe("ErrorBoundary: Save recovery copy", () => {
  beforeEach(() => { vi.resetModules(); vi.spyOn(console, "error").mockImplementation(() => {}); });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  async function mount(mode: string, wid: string | null) {
    const f = vi.fn(async (url: string, _init?: RequestInit) => new Response(
      url.endsWith("/config") ? JSON.stringify({ mode }) : "{}", { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", f);
    const { queryClient } = await import("../src/queryClient");
    const { useUi } = await import("../src/store");
    const { useToasts } = await import("../src/components/Toasts");
    const { ErrorBoundary } = await import("../src/components/ErrorBoundary");
    const { QueryClientProvider } = await import("@tanstack/react-query");
    queryClient.setQueryData(["config"], { mode });
    useUi.setState({ wid });
    useToasts.setState({ items: [] });
    const Bomb = () => { throw new Error("kaput"); };
    render(createElement(QueryClientProvider, { client: queryClient }, createElement(ErrorBoundary, null, createElement(Bomb))));
    return { f, useToasts };
  }

  it("klik zavolá POST /autosave a ukáže toast", async () => {
    const { f, useToasts } = await mount("desktop", "w9");
    fireEvent.click(screen.getByTestId("err-save-recovery"));
    await waitFor(() => expect(useToasts.getState().items.some((t) => t.kind === "ok")).toBe(true));
    expect(f.mock.calls.some(([u, i]) => String(u).endsWith("/workspaces/w9/autosave") && (i as RequestInit).method === "POST")).toBe(true);
  });
  it("ve veřejném režimu nebo bez wid tlačítko není", async () => {
    await mount("public", "w9");
    expect(screen.queryByTestId("err-save-recovery")).toBeNull();
    cleanup(); vi.resetModules();
    await mount("desktop", null);
    expect(screen.queryByTestId("err-save-recovery")).toBeNull();
  });
});
