import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { llmStatus, portal, portals } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

describe("Where your data goes", () => {
  it("lists Anthropic and only the sources that will run", async () => {
    server.use(
      http.get("/api/portals", () =>
        HttpResponse.json([
          ...portals(),
          portal({ id: "lever", name: "Lever", enabled: false }),
          portal({
            id: "custom-acme",
            name: "Acme Careers",
            kind: "plugin",
            custom: true,
            companies: null,
          }),
        ]),
      ),
    );
    await renderApp("/settings");
    const card = await screen.findByRole("region", { name: "Where your data goes" });
    expect(within(card).getByText("In use")).toBeVisible();
    const sources = await within(card).findByText(/Turned on:/);
    expect(sources).toHaveTextContent("Greenhouse (59 companies)");
    expect(sources).toHaveTextContent("Remote OK");
    expect(sources).toHaveTextContent("Acme Careers");
    // Keyed feeds without keys send nothing, so they aren't listed.
    expect(sources).not.toHaveTextContent("Adzuna");
    expect(within(card).getByText("GitHub")).toBeVisible();
  });

  it("says when Claude isn't connected and no sources are on", async () => {
    server.use(
      http.get("/api/llm/status", () => HttpResponse.json(llmStatus({ configured: false }))),
      http.get("/api/portals", () =>
        HttpResponse.json(portals().map((p) => ({ ...p, enabled: false }))),
      ),
    );
    await renderApp("/settings");
    const card = await screen.findByRole("region", { name: "Where your data goes" });
    expect(within(card).getByText("Not in use")).toBeVisible();
    expect(await within(card).findByText(/None are turned on/)).toBeVisible();
  });
});
