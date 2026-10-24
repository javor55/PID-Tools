// Seznam technik APC (pořadí jako v desktopu). Nová technika = soubor s komponentou `Main` (případně `Side`) a řádek zde;
// bez `Main` se zobrazí zástupný text (API ještě není).
import { FeedforwardMain } from "./Feedforward";
import { RatioMain, RatioSide } from "./Ratio";
import { RgaMain } from "./Rga";
import { SmithMain, SmithSide } from "./Smith";
import { SplitMain, SplitSide } from "./Split";
import { VpcMain, VpcSide } from "./Vpc";
import type { Technique } from "./common";

export const TECHNIQUES: Technique[] = [
  { id: "cascade", label: "apc_cascade" },
  { id: "ff", label: "apc_ff", intro: "apc_intro_ff", Main: FeedforwardMain },
  { id: "decouple", label: "apc_decouple", intro: "apc_intro_decouple" },
  { id: "override", label: "apc_override", intro: "apc_intro_override" },
  { id: "smith", label: "apc_smith", intro: "apc_intro_smith", Main: SmithMain, Side: SmithSide },
  { id: "gainsched", label: "apc_gainsched", intro: "apc_intro_gainsched" },
  { id: "gs_er", label: "gs_x_er" },
  { id: "split", label: "apc_split", intro: "apc_intro_split", Main: SplitMain, Side: SplitSide },
  { id: "vpc", label: "apc_vpc", intro: "apc_intro_vpc", Main: VpcMain, Side: VpcSide },
  { id: "ratio", label: "apc_ratio", intro: "apc_intro_ratio", Main: RatioMain, Side: RatioSide },
  { id: "rga", label: "apc_rga", intro: "apc_intro_rga", Main: RgaMain },
];

export const technique = (id: string) => TECHNIQUES.find((t) => t.id === id) ?? TECHNIQUES[0];
