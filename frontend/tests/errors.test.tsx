// ErrorBoundary (náhradní obsah, reset tlačítkem i klíčem) a úložiště oznámení (deduplikace, limit 4).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "../src/components/ErrorBoundary";
import { MAX_TOASTS, useToasts } from "../src/components/Toasts";

let boom = true;
function Bomb() {
  if (boom) throw new Error("kaput");
  return <p>obsah ok</p>;
}
const wrap = (ui: React.ReactNode) => <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>;

describe("ErrorBoundary", () => {
  beforeEach(() => { boom = true; vi.spyOn(console, "error").mockImplementation(() => {}); });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("shows fallback with the error text; Try again re-renders the content", () => {
    render(wrap(<ErrorBoundary resetKey="a"><Bomb /></ErrorBoundary>));
    expect(screen.getByTestId("err-boundary-msg").textContent).toBe("kaput");
    boom = false;
    fireEvent.click(screen.getByTestId("err-boundary-retry"));
    expect(screen.getByText("obsah ok")).toBeTruthy();
    expect(screen.queryByTestId("err-boundary")).toBeNull();
  });

  it("a changed resetKey clears the error", () => {
    const { rerender } = render(wrap(<ErrorBoundary resetKey="a"><Bomb /></ErrorBoundary>));
    expect(screen.getByTestId("err-boundary")).toBeTruthy();
    boom = false;
    rerender(wrap(<ErrorBoundary resetKey="b"><Bomb /></ErrorBoundary>));
    expect(screen.getByText("obsah ok")).toBeTruthy();
  });
});

describe("useToasts", () => {
  beforeEach(() => useToasts.setState({ items: [] }));

  it("does not repeat a text that is already shown", () => {
    const { push } = useToasts.getState();
    push({ kind: "err", text: "samp: must be > 0" });
    push({ kind: "err", text: "samp: must be > 0" });
    expect(useToasts.getState().items).toHaveLength(1);
  });

  it("keeps at most 4, dropping the oldest", () => {
    const { push } = useToasts.getState();
    for (let i = 0; i < 6; i++) push({ kind: "err", text: `e${i}` });
    const t = useToasts.getState().items.map((x) => x.text);
    expect(t).toHaveLength(MAX_TOASTS);
    expect(t).toEqual(["e2", "e3", "e4", "e5"]);
  });

  it("an ok toast disappears after 4 s, an error stays until dismissed", () => {
    vi.useFakeTimers();
    const { push, dismiss } = useToasts.getState();
    push({ kind: "ok", text: "saved" });
    push({ kind: "err", text: "bad" });
    act(() => { vi.advanceTimersByTime(4100); });
    expect(useToasts.getState().items.map((x) => x.text)).toEqual(["bad"]);
    dismiss(useToasts.getState().items[0].id);
    expect(useToasts.getState().items).toHaveLength(0);
    vi.useRealTimers();
  });
});
