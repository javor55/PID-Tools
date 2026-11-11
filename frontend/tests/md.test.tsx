// Md: tabulky v zápisu GitHub (záhlaví, oddělovač, zarovnání) a zachování odstavců, seznamů a zvýraznění.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Md } from "../src/components/Ui";

describe("Md", () => {
  it("renders a pipe table with header, alignment and inline formatting", () => {
    const { container } = render(<Md text={"| Metoda | Kdy | Číslo |\n|:---|:---:|---:|\n| **SIMC** | výchozí \\| volba | `1` |\n| Lambda | hladiny | 2 |"} />);
    expect(container.querySelector("table")).not.toBeNull();
    expect([...container.querySelectorAll("thead th")].map((e) => e.textContent)).toEqual(["Metoda", "Kdy", "Číslo"]);
    const rows = container.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(2);
    expect(rows[0].querySelector("b")?.textContent).toBe("SIMC");
    expect(rows[0].querySelectorAll("td")[1].textContent).toBe("výchozí | volba");
    expect(rows[0].querySelector("code")?.textContent).toBe("1");
    const th = container.querySelectorAll("thead th");
    expect((th[1] as HTMLElement).style.textAlign).toBe("center");
    expect((th[2] as HTMLElement).style.textAlign).toBe("right");
  });

  it("keeps text around a table and does not turn a lone pipe line into one", () => {
    const { container } = render(<Md text={"Úvod\n| a | b |\n|---|---|\n| 1 | 2 |\nZávěr\n\na | b bez oddělovače"} />);
    expect(container.querySelectorAll("table")).toHaveLength(1);
    expect(container.textContent).toContain("Úvod");
    expect(container.textContent).toContain("Závěr");
    expect(container.textContent).toContain("a | b bez oddělovače");
  });

  it("still renders lists, headings and emphasis", () => {
    const { container } = render(<Md text={"## Nadpis\n\n- jedna\n- *dvě*\n\n1. x\n2. y"} />);
    expect(container.querySelector("h4")?.textContent).toBe("Nadpis");
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(container.querySelector("li i")?.textContent).toBe("dvě");
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
  });
});
