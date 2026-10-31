import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { PortalDefinition, PortalTestResult } from "@/api/queries";
import { portal, portals } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const rss: PortalDefinition = {
  kind: "rss",
  id: "northwind",
  name: "Northwind",
  source_url: "https://northwind.example/careers",
  company: null,
  feed_url: "https://northwind.example/jobs.rss",
  company_in_title: null,
};

const testResult = (overrides: Partial<PortalTestResult> = {}): PortalTestResult => ({
  ok: true,
  count: 12,
  samples: [
    {
      external_id: "nw-1",
      url: "https://northwind.example/jobs/1",
      company: "Northwind",
      title: "Data Analyst",
      location: "Remote",
      remote: true,
      salary_text: null,
      description: "",
      posted_at: null,
    },
  ],
  errors: [],
  error: null,
  plugin_source: '"""Custom job source: Northwind"""\n\nDEFINITION = {"kind": "rss"}\n',
  definition_json: "{}",
  definition: rss,
  ...overrides,
});

async function open() {
  const view = await renderApp("/sources");
  await view.user.click(await screen.findByRole("button", { name: "Add a job site" }));
  const dialog = await screen.findByRole("dialog", { name: "Add a job site" });
  return { ...view, dialog };
}

describe("Add a job site", () => {
  it("detects a feed, shows samples and the plugin file, then adds it", async () => {
    let added: unknown = null;
    const tested: PortalDefinition[] = [];
    server.use(
      http.post("/api/portals/inspect", () =>
        HttpResponse.json({
          url: rss.source_url,
          final_url: rss.source_url,
          page_title: "Northwind",
          candidates: [
            {
              kind: "rss",
              title: "Job feed (RSS/Atom)",
              detail: "The page links a feed.",
              definition: rss,
              ats: null,
              slug: null,
            },
          ],
          error: null,
        }),
      ),
      http.post("/api/portals/test", async ({ request }) => {
        const { definition } = (await request.json()) as { definition: PortalDefinition };
        tested.push(definition);
        // The first run settles how titles carry the company; later runs echo the choice.
        const settled =
          definition.kind === "rss" && definition.company_in_title === null
            ? { ...definition, company_in_title: "prefix_colon" as const }
            : definition;
        return HttpResponse.json(testResult({ definition: settled }));
      }),
      http.post("/api/portals/custom", async ({ request }) => {
        added = await request.json();
        return HttpResponse.json(
          portal({ id: "custom-northwind", name: "Northwind Jobs", kind: "plugin", custom: true }),
          { status: 201 },
        );
      }),
    );
    const { user, dialog } = await open();
    await user.type(within(dialog).getByLabelText("Careers page URL"), rss.source_url);
    await user.click(within(dialog).getByRole("button", { name: "Look at this page" }));
    expect(await within(dialog).findByText("Job feed (RSS/Atom)")).toBeVisible();

    await user.click(within(dialog).getByRole("button", { name: "Test it" }));
    expect(await within(dialog).findByText("Found 12 jobs. Here are the first few.")).toBeVisible();
    expect(within(dialog).getByRole("link", { name: "Data Analyst" })).toHaveAttribute(
      "href",
      "https://northwind.example/jobs/1",
    );
    await user.click(within(dialog).getByText("Plugin file it will create"));
    expect(within(dialog).getByText(/DEFINITION =/)).toBeVisible();

    const company = within(dialog).getByRole("combobox", { name: "Company in job titles" });
    expect(company).toHaveTextContent("Company: Job title");
    await user.click(company);
    await user.click(await screen.findByRole("option", { name: "Job title, Company" }));
    await waitFor(() => {
      expect(tested.at(-1)).toEqual({ ...rss, company_in_title: "suffix_comma" });
    });

    const name = await within(dialog).findByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Northwind Jobs");
    await user.click(within(dialog).getByRole("button", { name: "Add source" }));
    await waitFor(() => {
      expect(added).toEqual({
        definition: { ...rss, name: "Northwind Jobs", company_in_title: "suffix_comma" },
      });
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("sends known job boards to the watchlist", async () => {
    let body: unknown = null;
    server.use(
      http.post("/api/portals/inspect", () =>
        HttpResponse.json({
          url: "https://jobs.lever.co/plaid",
          final_url: "https://jobs.lever.co/plaid",
          page_title: null,
          candidates: [
            {
              kind: "watchlist",
              title: "Lever job board",
              detail: "Add 'plaid'.",
              definition: null,
              ats: "lever",
              slug: "plaid",
            },
          ],
          error: null,
        }),
      ),
      http.post("/api/companies", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json([], { status: 201 });
      }),
    );
    const { user, dialog } = await open();
    await user.type(
      within(dialog).getByLabelText("Careers page URL"),
      "https://jobs.lever.co/plaid",
    );
    await user.click(within(dialog).getByRole("button", { name: "Look at this page" }));
    await user.click(await within(dialog).findByRole("button", { name: "Add to watchlist" }));
    await waitFor(() => {
      expect(body).toEqual({ ats: "lever", companies: [{ slug: "plaid" }] });
    });
  });

  it("asks Claude when nothing is detected, and refuses sources with too few jobs", async () => {
    server.use(
      http.post("/api/portals/inspect", () =>
        HttpResponse.json({
          url: "https://tiny.example",
          final_url: "https://tiny.example",
          page_title: "Tiny",
          candidates: [],
          error: null,
        }),
      ),
      http.post("/api/portals/draft", () =>
        HttpResponse.json({
          kind: "html",
          title: "Page layout (CSS)",
          detail: "Jobs are cards.",
          definition: {
            kind: "html",
            id: "tiny",
            name: "Tiny",
            source_url: "https://tiny.example",
            company: null,
            list_url: "https://tiny.example",
            item_selector: ".job",
            fields: { title: "h3", link: null, location: null, company: null },
          },
          ats: null,
          slug: null,
        }),
      ),
      http.post("/api/portals/test", () =>
        HttpResponse.json(
          testResult({ ok: false, count: 2, error: "Found 2 jobs; a source needs at least 3." }),
        ),
      ),
    );
    const { user, dialog } = await open();
    await user.type(within(dialog).getByLabelText("Careers page URL"), "https://tiny.example");
    await user.click(within(dialog).getByRole("button", { name: "Look at this page" }));
    expect(
      await within(dialog).findByText("No feed or structured job data on this page."),
    ).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Ask Claude to read the layout" }));
    await user.click(await within(dialog).findByRole("button", { name: "Test it" }));
    expect(
      await within(dialog).findByText("Found 2 jobs; a source needs at least 3."),
    ).toBeVisible();
    expect(within(dialog).queryByRole("button", { name: "Add source" })).not.toBeInTheDocument();
  });
});

describe("Your sources", () => {
  it("lists custom sources and removes one after confirming", async () => {
    let deleted = false;
    server.use(
      http.get("/api/portals", () =>
        HttpResponse.json([
          ...portals(),
          portal({
            id: "custom-northwind",
            name: "Northwind",
            kind: "plugin",
            custom: true,
            companies: null,
            docs_url: "https://northwind.example/careers",
          }),
        ]),
      ),
      http.delete("/api/portals/custom/northwind", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = await renderApp("/sources");
    const section = await screen.findByRole("region", { name: "Your sources" });
    expect(within(section).getByText("Northwind")).toBeVisible();
    await user.click(within(section).getByRole("button", { name: "Remove source" }));
    await user.click(within(section).getByRole("button", { name: "Remove" }));
    await waitFor(() => {
      expect(deleted).toBe(true);
    });
  });
});
