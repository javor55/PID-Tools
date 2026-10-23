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
declare module "*/viewer_an.js";
declare module "*/trend.js" {
  import type { ViewerComponent } from "*/viewer.js";
  const mount: (component: ViewerComponent) => void;
  export default mount;
}
