// Mapa prvků Modelu na podzáložky (FEATURE-005) a uložení zvolené podzáložky.
import { describe, expect, it } from "vitest";
import { MODEL_SUBS, modelSubOf, useUi } from "../src/store";

describe("modelSubOf", () => {
  it("přiřadí prvky hlavní plochy podzáložkám", () => {
    expect(modelSubOf("model-trend")).toBe("ident");
    expect(modelSubOf("dist-use-0-P1D")).toBe("ident");
    expect(modelSubOf("val-fit-pv")).toBe("validate");
    expect(modelSubOf("step-chart")).toBe("validate");
    expect(modelSubOf("validation")).toBe("residuals");
    expect(modelSubOf("unc-rel-2")).toBe("residuals");
    expect(modelSubOf("residuals")).toBe("residuals");
  });
  it("prvky mimo hlavní plochu Modelu nemají podzáložku", () => {
    expect(modelSubOf("identify")).toBeNull();
    expect(modelSubOf("set1-gain")).toBeNull();
  });
});

describe("setModelSub", () => {
  it("přepne záložku na Model a uloží volbu", () => {
    useUi.getState().setTab("data");
    useUi.getState().setModelSub(MODEL_SUBS[1]);
    expect(useUi.getState().tab).toBe("model");
    expect(useUi.getState().modelSub).toBe("validate");
    expect(localStorage.getItem("pid.msub")).toBe('"validate"');
  });
});
