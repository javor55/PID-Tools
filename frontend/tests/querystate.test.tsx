// QueryState (načítání / chyba / prázdno / data / přepočet) a Card busy.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { Card } from "../src/components/Card";
import { QueryState, type QueryLike } from "../src/components/QueryState";

// texty dodává server; v testu vrací překlad klíč
vi.mock("../src/i18n", () => ({ useT: () => (k: string) => k }));
const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
const base: QueryLike<number[]> = { data: undefined, isPending: false, isError: false, error: null, isFetching: false, refetch: () => {} };
afterEach(cleanup);

describe("QueryState", () => {
  it("loading without data shows a skeleton with role=status, not the ellipsis", () => {
    wrap(<QueryState q={{ ...base, isPending: true, isFetching: true }}>{() => <p>x</p>}</QueryState>);
    const s = screen.getByRole("status");
    expect(s.className).toContain("qs-skeleton");
    expect(s.textContent).toContain("qs_loading");
    expect(s.textContent).not.toContain("…");
  });

  it("error shows the message and Try again calls refetch", () => {
    const refetch = vi.fn();
    wrap(<QueryState q={{ ...base, isError: true, error: new Error("kaput"), refetch }}>{() => <p>x</p>}</QueryState>);
    expect(screen.getByText("kaput")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "qs_retry" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("409 shows the need_model empty state instead of an error", () => {
    wrap(<QueryState q={{ ...base, isError: true, error: new ApiError(409, "no model") }}>{() => <p>x</p>}</QueryState>);
    expect(screen.getByTestId("qs-empty").textContent).toContain("need_model");
    expect(screen.queryByTestId("qs-error")).toBeNull();
  });

  it("empty shows the text and an action", () => {
    const onClick = vi.fn();
    wrap(<QueryState q={{ ...base, data: [] }} empty={(d) => d.length === 0} emptyText="Nic tu není"
      action={{ label: "Go to Model", onClick }}>{() => <p>x</p>}</QueryState>);
    expect(screen.getByText("Nic tu není")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to Model" }));
    expect(onClick).toHaveBeenCalled();
  });

  it("data renders children; isFetching with data sets aria-busy", () => {
    const { container, rerender } = wrap(<QueryState q={{ ...base, data: [1, 2] }}>{(d) => <p>n={d.length}</p>}</QueryState>);
    expect(screen.getByText("n=2")).toBeTruthy();
    expect(container.querySelector("[aria-busy]")).toBeNull();
    rerender(<QueryClientProvider client={new QueryClient()}>
      <QueryState q={{ ...base, data: [1, 2], isFetching: true }}>{(d) => <p>n={d.length}</p>}</QueryState></QueryClientProvider>);
    const busy = container.querySelector("[aria-busy='true']");
    expect(busy?.className).toContain("is-busy");
    expect(screen.getByText("n=2")).toBeTruthy();
  });
});

describe("Card busy", () => {
  it("busy sets aria-busy and is-busy; without busy there is no attribute", () => {
    wrap(<Card title="A" testid="a" busy>obsah</Card>);
    expect(screen.getByTestId("a").getAttribute("aria-busy")).toBe("true");
    expect(screen.getByTestId("a").className).toContain("is-busy");
    cleanup();
    wrap(<Card title="B" testid="b">obsah</Card>);
    expect(screen.getByTestId("b").hasAttribute("aria-busy")).toBe(false);
  });
});
