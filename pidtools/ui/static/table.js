// Tabulka aplikace (vzhled podle návrhu): záhlaví, řádky s jemnými čarami, čísla vpravo písmem s pevnou šířkou,
// zvýrazněné buňky, volitelně výběr řádku klepnutím (stav „sel“ → Python).
export default function (component) {
  const { data, parentElement: root } = component;
  root.querySelectorAll(".pidt-wrap").forEach((n) => n.remove());
  const D = data || {};
  const wrap = document.createElement("div");
  wrap.className = "pidt-wrap" + (D.dark ? " dark" : "");
  if (D.height) wrap.style.maxHeight = D.height + "px";
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const cols = D.cols || [];
  let h = "<table class='pidt'><thead><tr>";
  cols.forEach((c) => { h += `<th class="${c.num ? "n" : ""}"${c.help ? ` title="${esc(c.help)}"` : ""}>${esc(c.name)}</th>`; });
  h += "</tr></thead><tbody>";
  (D.rows || []).forEach((r, i) => {
    const rc = [(D.select ? "click" : ""), (i === D.sel ? "sel" : ""), (D.rcls && D.rcls[i]) || ""].join(" ");
    h += `<tr class="${rc}" data-i="${i}">`;
    r.forEach((v, j) => {
      const st = D.sty && D.sty[i] && D.sty[i][j];
      const cl = [(cols[j] && cols[j].num ? "n" : ""), (D.ccls && D.ccls[i] && D.ccls[i][j]) || ""].join(" ");
      h += `<td class="${cl}"${st ? ` style="${esc(st)}"` : ""}>${esc(v)}</td>`;
    });
    h += "</tr>";
  });
  h += "</tbody></table>";
  wrap.innerHTML = h;
  root.appendChild(wrap);
  if (D.select) {
    wrap.querySelectorAll("tbody tr").forEach((tr) => {
      tr.onclick = () => {
        const i = +tr.dataset.i;
        wrap.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
        tr.classList.add("sel");
        component.setStateValue("sel", i);
      };
    });
  }
}
