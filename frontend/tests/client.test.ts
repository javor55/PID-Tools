// Klient API: jedna cesta požadavků, text chyby z `detail`, předání AbortSignal.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Client = typeof import("../src/api/client");
type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

let fetchMock: ReturnType<typeof vi.fn>;

/** Čerstvý modul (cache relace `ensureSession` je modulová) a fetch, který obslouží `/config` i testovanou cestu. */
async function setup(handler: Handler): Promise<Client> {
  vi.resetModules();
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/config")) return new Response(JSON.stringify({ mode: "desktop" }), { status: 200, headers: { "content-type": "application/json" } });
    return handler(url, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return import("../src/api/client");
}

const jsonErr = (detail: unknown, status = 422) =>
  new Response(JSON.stringify({ detail }), { status, statusText: "Unprocessable", headers: { "content-type": "application/json" } });

function callers(c: Client): Record<string, () => Promise<unknown>> {
  return {
    request: () => c.request("POST", "/x", { a: 1 }),
    rawRequest: () => c.rawRequest("POST", "/x", new ArrayBuffer(2)),
    binary: () => c.binary("/x", { a: 1 }),
    bytes: () => c.bytes("POST", "/x", { a: 1 }),
  };
}

beforeEach(() => { vi.restoreAllMocks(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("API client errors", () => {
  it("all four functions throw ApiError with the server detail", async () => {
    const c = await setup(() => jsonErr("samp: must be > 0"));
    for (const [name, fn] of Object.entries(callers(c))) {
      const err = await fn().catch((e: unknown) => e);
      expect(err, name).toBeInstanceOf(c.ApiError);
      expect((err as InstanceType<Client["ApiError"]>).status, name).toBe(422);
      expect((err as Error).message, name).toBe("samp: must be > 0");
    }
  });

  it("object detail becomes JSON text", async () => {
    const detail = [{ loc: ["body", "samp"], msg: "bad" }];
    const c = await setup(() => jsonErr(detail));
    for (const [name, fn] of Object.entries(callers(c))) {
      const err = await fn().catch((e: unknown) => e);
      expect((err as Error).message, name).toBe(JSON.stringify(detail));
    }
  });

  it("a response without a JSON body falls back to statusText", async () => {
    const c = await setup(() => new Response("<html>oops</html>", { status: 502, statusText: "Bad Gateway" }));
    for (const [name, fn] of Object.entries(callers(c))) {
      const err = await fn().catch((e: unknown) => e);
      expect((err as InstanceType<Client["ApiError"]>).status, name).toBe(502);
      expect((err as Error).message, name).toBe("Bad Gateway");
    }
  });
});

describe("API client behaviour", () => {
  it("request returns undefined for 204", async () => {
    const c = await setup(() => new Response(null, { status: 204 }));
    expect(await c.request("DELETE", "/x")).toBeUndefined();
  });

  it("binary without a body is GET, with a body POST JSON", async () => {
    const c = await setup(() => new Response(new ArrayBuffer(3), { status: 200 }));
    await c.binary("/x");
    await c.binary("/x", { a: 1 });
    const calls = fetchMock.mock.calls.filter((a) => !String(a[0]).endsWith("/config"));
    expect(calls[0][1].method).toBe("GET");
    expect(calls[0][1].body).toBeUndefined();
    expect(calls[1][1].method).toBe("POST");
    expect(calls[1][1].body).toBe('{"a":1}');
  });
});

describe("API client AbortSignal", () => {
  it("passes the signal to fetch and an abort throws AbortError", async () => {
    const c = await setup((_url, init) => new Promise<Response>((_res, rej) => {
      init?.signal?.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
    }));
    const calls: Record<string, (s: AbortSignal) => Promise<unknown>> = {
      request: (s) => c.request("GET", "/x", undefined, s),
      rawRequest: (s) => c.rawRequest("POST", "/x", new ArrayBuffer(1), s),
      binary: (s) => c.binary("/x", undefined, s),
      bytes: (s) => c.bytes("GET", "/x", undefined, s),
    };
    for (const [name, fn] of Object.entries(calls)) {
      const ctl = new AbortController();
      const p = fn(ctl.signal).catch((e: unknown) => e);
      await vi.waitFor(() => expect(fetchMock.mock.calls.some((a) => a[1]?.signal === ctl.signal), name).toBe(true));
      ctl.abort();
      const err = await p;
      expect((err as Error).name, name).toBe("AbortError");
    }
  });
});
