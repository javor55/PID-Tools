// Data › Zdroje a smyčky (E4, deska docs/design/v2/DataSources.dc.html): soubory se společnou časovou osou a skládání
// smyček (mapování rolí na zdroj › sloupec). Hlavní plocha: karty Soubory a Smyčky; pravý panel: Sloupce ze souborů.
import "../../styles/sources.css";
import { ColumnsPanel } from "./sources/ColumnsPanel";
import { FilesCard } from "./sources/FilesCard";
import { LoopsCard } from "./sources/LoopsCard";
import { useSources } from "./sources/api";

export function SourcesMain() {
  const q = useSources();
  return (
    <div className="src-main" data-testid="sources-main">
      <FilesCard data={q.data} />
      <LoopsCard data={q.data} />
    </div>
  );
}

export function SourcesSide() {
  const q = useSources();
  return <ColumnsPanel data={q.data} />;
}
