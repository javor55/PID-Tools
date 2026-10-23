// Formát textů jako Python str.format (hodnoty ověřené v Pythonu).
import { describe, expect, it } from "vitest";
import { format, formatValue } from "../src/lib/format";

describe("formatValue", () => {
  it.each([
    [1.23456, ".4g", "1.235"], [1234567, ".4g", "1.235e+06"], [0.000012345, ".3g", "1.23e-05"],
    [100, ".4g", "100"], [0.5, "g", "0.5"], [2.0, "g", "2"], [24.579757873394527, ".0f", "25"],
    [0.30000000000000004, ".2f", "0.30"], [12.5, ".1f", "12.5"], [0, ".4g", "0"], [1e-5, "g", "1e-05"],
    [123456.7, "g", "123457"], [1234567.0, "g", "1.23457e+06"],
  ])("%s:%s → %s", (x, spec, out) => expect(formatValue(x, spec)).toBe(out));
});

describe("format", () => {
  it("fills names and keeps unknown placeholders", () => {
    expect(format("Gain {g} · TI {ti:.4g} s · {x}", { g: 2, ti: 210.123456 })).toBe("Gain 2 · TI 210.1 s · {x}");
  });
});
