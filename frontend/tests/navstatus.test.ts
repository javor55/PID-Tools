import { describe, expect, it } from "vitest";
import { navMark } from "../src/lib/navStatus";

describe("navMark", () => {
  it("vše splněno = ok", () => expect(navMark({ ok: 3, warn: 0, todo: 0 })).toBe("ok"));
  it("varování má přednost", () => expect(navMark({ ok: 3, warn: 1, todo: 2 })).toBe("warn"));
  it("něco ještě k provedení = bez značky", () => expect(navMark({ ok: 3, warn: 0, todo: 1 })).toBeNull());
  it("záložka bez položek = bez značky", () => expect(navMark({ ok: 0, warn: 0, todo: 0 })).toBeNull());
  it("bez dat = bez značky", () => expect(navMark(undefined)).toBeNull());
});
