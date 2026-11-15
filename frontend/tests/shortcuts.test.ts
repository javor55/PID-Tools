// Rozpoznání klávesových zkratek (FEATURE-001): čistá funkce matchShortcut bez DOM.
import { describe, expect, it } from "vitest";
import { type KeyLike, matchShortcut } from "../src/shortcuts";

const k = (key: string, m: Partial<KeyLike> = {}): KeyLike => ({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...m });

describe("matchShortcut", () => {
  it("Ctrl+S a Cmd+S ukládají (i s velkým písmenem při Caps Lock)", () => {
    expect(matchShortcut(k("s", { ctrlKey: true }))).toEqual({ kind: "save" });
    expect(matchShortcut(k("s", { metaKey: true }))).toEqual({ kind: "save" });
    expect(matchShortcut(k("S", { ctrlKey: true }))).toEqual({ kind: "save" });
  });
  it("F5 je Calculate, Ctrl+F5 a Shift+F5 zůstávají prohlížeči", () => {
    expect(matchShortcut(k("F5"))).toEqual({ kind: "calc" });
    expect(matchShortcut(k("F5", { ctrlKey: true }))).toBeNull();
    expect(matchShortcut(k("F5", { shiftKey: true }))).toBeNull();
  });
  it("Ctrl+R zůstává prohlížeči", () => expect(matchShortcut(k("r", { ctrlKey: true }))).toBeNull());
  it("Ctrl+1 … Ctrl+6 přepínají záložky podle pořadí", () => {
    for (let i = 1; i <= 6; i++) expect(matchShortcut(k(String(i), { ctrlKey: true }))).toEqual({ kind: "tab", index: i - 1 });
  });
  it("prosté číslice a Ctrl+7 / Ctrl+0 nejsou zkratky", () => {
    expect(matchShortcut(k("1"))).toBeNull();
    expect(matchShortcut(k("3"))).toBeNull();
    expect(matchShortcut(k("7", { ctrlKey: true }))).toBeNull();
    expect(matchShortcut(k("0", { ctrlKey: true }))).toBeNull();
  });
  it("Alt+šipky přepínají smyčku", () => {
    expect(matchShortcut(k("ArrowUp", { altKey: true }))).toEqual({ kind: "loop", dir: -1 });
    expect(matchShortcut(k("ArrowDown", { altKey: true }))).toEqual({ kind: "loop", dir: 1 });
    expect(matchShortcut(k("ArrowUp"))).toBeNull();
    expect(matchShortcut(k("ArrowDown", { ctrlKey: true }))).toBeNull();
  });
  it("Ctrl+P otevře záložku Projekt", () => expect(matchShortcut(k("p", { ctrlKey: true }))).toEqual({ kind: "project" }));
  it("Ctrl+Shift+S není zkratka (patří prohlížeči)", () => {
    expect(matchShortcut(k("S", { ctrlKey: true, shiftKey: true }))).toBeNull();
  });
  it("Ctrl+Alt+znak (AltGr) a prosté písmeno nejsou zkratky", () => {
    expect(matchShortcut(k("s", { ctrlKey: true, altKey: true }))).toBeNull();
    expect(matchShortcut(k("s"))).toBeNull();
  });
});
