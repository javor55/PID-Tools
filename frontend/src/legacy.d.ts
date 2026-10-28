// Sdílené moduly dnešního webu (pidtools/ui/static) – čisté JS, používá je i Streamlit.
declare module "*/viewer.js" {
  export interface ViewerComponent {
    data: Record<string, unknown>;
    parentElement: HTMLElement;
    setStateValue: (key: string, value: unknown) => void;
    setTriggerValue?: (key: string, value: unknown) => void;
  }
  const mount: (component: ViewerComponent) => void;
  export default mount;
}
declare module "*/viewer_an.js" {
  const an: unknown;
  export default an;
}
declare module "*/trend.js" {
  import type { ViewerComponent } from "*/viewer.js";
  const mount: (component: ViewerComponent) => void;
  export default mount;
}
declare module "*/live_engine.js" {
  const engine: unknown;
  export default engine;
}
declare module "*/live_ui.js" {
  export interface LiveComponent {
    data: Record<string, unknown>;
    parentElement: HTMLElement;
    setTriggerValue: (name: string, value: unknown) => void;
  }
  /** Vrací funkci pro odpojení (zastaví animaci a odpojí posluchače). */
  const mount: (component: LiveComponent) => () => void;
  export default mount;
}
