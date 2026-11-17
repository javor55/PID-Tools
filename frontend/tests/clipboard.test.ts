// Schránka (FEATURE-002): tableToTsv a copyText (s navigator.clipboard i záložní cestou přes execCommand).
import { afterEach, describe, expect, it, vi } from "vitest";
import { copyText, tableToTsv } from "../src/lib/clipboard";

const table = (html: string): HTMLTableElement => {
  document.body.innerHTML = `<table>${html}</table>`;
  return document.querySelector("table") as HTMLTableElement;
};

describe("tableToTsv", () => {
  it("bere thead + tbody, ne tfoot; buňky odděluje tabulátorem", () => {
    const t = table(`<thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></tbody>
      <tfoot><tr><td>sum</td><td>9</td></tr></tfoot>`);
    expect(tableToTsv(t)).toBe("A\tB\n1\t2\n3\t4");
  });
  it("nové řádky a tabulátory uvnitř buňky nahradí mezerou a text ořízne", () => {
    const t = table(`<tbody><tr><td>  a\nb\tc  </td><td>x</td></tr></tbody>`);
    expect(tableToTsv(t)).toBe("a b c\tx");
  });
  it("skrytý řádek vynechá", () => {
    const t = table(`<tbody><tr><td>1</td></tr><tr style="display: none"><td>2</td></tr><tr><td>3</td></tr></tbody>`);
    expect(tableToTsv(t)).toBe("1\n3");
  });
});

describe("copyText", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = ""; });

  it("použije navigator.clipboard.writeText", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    await copyText("ahoj");
    expect(writeText).toHaveBeenCalledWith("ahoj");
  });

  it("bez navigator.clipboard použije skrytý textarea + execCommand", async () => {
    vi.stubGlobal("navigator", {});
    let copied = "";
    const exec = vi.fn((cmd: string) => { copied = (document.querySelector("textarea") as HTMLTextAreaElement).value; return cmd === "copy"; });
    Object.defineProperty(document, "execCommand", { value: exec, configurable: true });
    await copyText("záloha");
    expect(exec).toHaveBeenCalledWith("copy");
    expect(copied).toBe("záloha");
    expect(document.querySelector("textarea")).toBeNull();      // pomocný prvek se odstraní
  });

  it("když writeText selže, zkusí zálohu; když selže i ta, vyhodí chybu", async () => {
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
    Object.defineProperty(document, "execCommand", { value: vi.fn(() => false), configurable: true });
    await expect(copyText("x")).rejects.toThrow();
  });
});
