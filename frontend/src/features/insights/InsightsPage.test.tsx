import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { insights } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

import { compactNumber, pct, weekLabel } from "./insightsText";

describe("Insights", () => {
  it("shows headline numbers, charts, and their tables", async () => {
    server.use(http.get("/api/insights", () => HttpResponse.json(insights())));
    const { user } = await renderApp("/insights");
    const tile = (await screen.findByText("Response rate")).parentElement;
    expect(tile).toHaveTextContent("Response rate67%2 responses");
    expect(screen.getByRole("progressbar", { name: "Share of monthly cap used" })).toBeVisible();
    expect(screen.getByText("of your $20.00 cap")).toBeVisible();

    for (const title of [
      "Pipeline funnel",
      "Response rate by source",
      "Applications sent per week",
      "AI spend by command this month",
    ]) {
      expect(screen.getByRole("img", { name: title })).toBeInTheDocument();
    }
    const funnelCard = screen
      .getByText("Pipeline funnel", { selector: "[data-slot=card-title]" })
      .closest<HTMLElement>("[data-slot=card]");
    if (!funnelCard) throw new Error("no funnel card");
    await user.click(within(funnelCard).getByText("Show as a table"));
    const table = within(funnelCard).getByRole("table");
    expect(table).toHaveTextContent("Applied375%");
  });

  it("teaches the next steps before there's anything to chart", async () => {
    await renderApp("/insights");
    expect(await screen.findByRole("heading", { name: "Nothing to chart yet" })).toBeVisible();
    expect(screen.getByText("AI spend this month")).toBeVisible();
  });

  it("exports a self-contained HTML report", async () => {
    let called = false;
    server.use(
      http.get("/api/insights", () => HttpResponse.json(insights())),
      http.post("/api/reports", () => {
        called = true;
        return HttpResponse.json({
          filename: "offerbound-report-2026-10-31.html",
          path: "/Users/ada/Offerbound/reports/offerbound-report-2026-10-31.html",
          size: 12_000,
        });
      }),
    );
    const { user } = await renderApp("/insights");
    await user.click(await screen.findByRole("button", { name: "Export HTML report" }));
    await waitFor(() => {
      expect(called).toBe(true);
    });
    expect(await screen.findByRole("link", { name: "Download report" })).toHaveAttribute(
      "href",
      "/api/reports/offerbound-report-2026-10-31.html",
    );
  });
});

describe("insights helpers", () => {
  it("formats numbers", () => {
    expect(pct(null)).toBe("–");
    expect(pct(2 / 3)).toBe("67%");
    expect(weekLabel("2026-10-05")).toBe("Oct 5");
    expect(compactNumber(2524)).toBe("2,524");
    expect(compactNumber(25_240)).toBe("25.2K");
  });
});
