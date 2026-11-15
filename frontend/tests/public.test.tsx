// Veřejný režim: upozornění na soukromí a skrytí OPC UA podle `/config`.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { PublicNotice } from "../src/deploy";
import { useUi } from "../src/store";
import { OpcButton } from "../src/tabs/OpcDialog";

function wrap(mode: string, ui: ReactNode) {
  const qc = new QueryClient();
  qc.setQueryData(["config"], { mode, max_upload_mb: 20, session_ttl_min: 120 });
  qc.setQueryData(["i18n", useUi.getState().lang], { pub_notice_short: "SHORT NOTICE", pub_notice_title: "TITLE", pub_notice: "Gone after {min} min", opc_menu: "OPC UA" });
  qc.setQueryData(["opc-available"], true);
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

afterEach(cleanup);

describe("public mode UI", () => {
  it("shows the privacy notice and hides the OPC UA button", () => {
    wrap("public", <><PublicNotice short /><PublicNotice /><OpcButton /></>);
    expect(screen.getByTestId("public-notice").textContent).toBe("SHORT NOTICE");
    expect(screen.getByTestId("public-notice-help").textContent).toContain("Gone after 120 min");
    expect(screen.queryByTestId("opc-open")).toBeNull();
  });

  it("desktop and team modes show no notice and keep OPC UA", () => {
    for (const mode of ["desktop", "team"]) {
      const { unmount } = wrap(mode, <><PublicNotice short /><OpcButton /></>);
      expect(screen.queryByTestId("public-notice")).toBeNull();
      expect(screen.getByTestId("opc-open")).toBeTruthy();
      unmount();
    }
  });
});
