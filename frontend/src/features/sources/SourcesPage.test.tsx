import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { PortalView } from "@/api/queries";
import { FakeEventSource } from "@/test/fakeEventSource";
import {
  company,
  portalRun,
  portals,
  profileOverview,
  scrapeSummary,
  searchTarget,
  task,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

function withTargets() {
  server.use(
    http.get("/api/profile", () =>
      HttpResponse.json(profileOverview({ search_targets: [searchTarget()] })),
    ),
  );
}

function card(name: string): HTMLElement {
  const label = screen.getByText(name, { selector: "label" });
  const element = label.closest<HTMLElement>("[data-slot=card]");
  if (!element) throw new Error(`no card for ${name}`);
  return element;
}

describe("SourcesPage", () => {
  it("shows a card per source with risk, status, and counts", async () => {
    server.use(
      http.get("/api/portals", () =>
        HttpResponse.json(
          portals().map((p) =>
            p.id === "remoteok"
              ? { ...p, status: "error", last_error: "HTTP 503 after 4 attempts" }
              : p.id === "greenhouse"
                ? { ...p, jobs_found: 1725, last_run_at: new Date().toISOString(), status: "ok" }
                : p,
          ),
        ),
      ),
    );
    await renderApp("/sources");
    expect(await screen.findByRole("heading", { name: "Sources", level: 1 })).toBeInTheDocument();
    const boards = screen.getByRole("region", { name: "Company job boards" });
    expect(within(boards).getAllByText("Low risk")).toHaveLength(4);

    const greenhouse = card("Greenhouse");
    expect(greenhouse).toHaveTextContent("Searched just now");
    expect(greenhouse).toHaveTextContent("Jobs found1,725");
    expect(within(greenhouse).getByRole("button", { name: "59 companies" })).toBeInTheDocument();
    expect(card("Remote OK")).toHaveTextContent("Last search failed: HTTP 503 after 4 attempts");
    expect(card("Adzuna")).toHaveTextContent("Needs an app ID, an app key");
    expect(card("USAJOBS")).toHaveTextContent("US only");
  });

  it("keeps sources that need a developer key under Advanced until one is set up", async () => {
    await renderApp("/sources");
    const feeds = await screen.findByRole("region", { name: "Job feeds" });
    const advanced = within(feeds).getByText("Advanced: more sources that need a developer key");
    const details = advanced.closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveTextContent("Adzuna");
    expect(details).toHaveTextContent("USAJOBS");
    expect(details).not.toHaveTextContent("Remote OK");
    expect(feeds).toHaveTextContent("Searched by job title. Nothing to set up.");
  });

  it("switches a source off", async () => {
    let body: unknown = null;
    server.use(
      http.patch("/api/portals/:id", async ({ request, params }) => {
        body = await request.json();
        const updated = portals().find((p) => p.id === params.id);
        return HttpResponse.json({ ...updated, enabled: false });
      }),
    );
    const { user } = await renderApp("/sources");
    const toggle = await screen.findByRole("switch", { name: "We Work Remotely" });
    expect(toggle).toBeChecked();
    await user.click(toggle);
    await waitFor(() => {
      expect(toggle).not.toBeChecked();
    });
    expect(body).toEqual({ enabled: false });
  });

  it("saves API keys to the keychain without showing them again", async () => {
    let saved: unknown = null;
    server.use(
      http.put("/api/portals/usajobs/credentials", async ({ request }) => {
        saved = await request.json();
        const usajobs = portals().find((p) => p.id === "usajobs");
        return HttpResponse.json<PortalView>({
          ...(usajobs as PortalView),
          ready: true,
          missing: [],
          config: { email: "ada@example.com" },
        });
      }),
    );
    const { user } = await renderApp("/sources");
    const form = await screen.findByRole("form", { name: "USAJOBS API key" });
    const key = within(form).getByLabelText("API key");
    expect(key).toHaveAttribute("type", "password");
    const save = within(form).getByRole("button", { name: "Save key" });
    expect(save).toBeDisabled();
    await user.type(key, "usa-secret");
    await user.type(within(form).getByLabelText("Email the key was issued to"), "ada@example.com");
    await user.click(save);

    expect(await within(card("USAJOBS")).findByText("Key saved in your keychain")).toBeVisible();
    expect(saved).toEqual({
      secrets: { api_key: "usa-secret" },
      config: { email: "ada@example.com" },
    });
    expect(screen.queryByDisplayValue("usa-secret")).not.toBeInTheDocument();
    expect(
      within(card("USAJOBS")).queryByRole("link", { name: /Get a free key/ }),
    ).not.toBeInTheDocument();
  });

  it("asks for search targets before it can search", async () => {
    await renderApp("/sources");
    expect(await screen.findByRole("button", { name: "Search now" })).toBeDisabled();
    expect(screen.getByText("Add the job titles you're looking for first.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Set targets in Profile" })).toHaveAttribute(
      "href",
      "/profile",
    );
  });

  it("runs a search with live progress, then shows results by source", async () => {
    withTargets();
    let started = false;
    server.use(
      http.post("/api/scrape", () => {
        started = true;
        return HttpResponse.json({ task_id: "s1" }, { status: 202 });
      }),
      http.get("/api/scrape/last", () =>
        HttpResponse.json(
          started
            ? scrapeSummary({
                new: 14,
                removed: 3462,
                portals: [
                  portalRun({ new: 12, errors: ["gone: not found on this ATS"] }),
                  portalRun({
                    portal_id: "adzuna",
                    name: "Adzuna",
                    status: "skipped",
                    detail: "needs an app ID",
                    found: 0,
                    matched: 0,
                    new: 0,
                  }),
                ],
              })
            : null,
        ),
      ),
    );
    const { user } = await renderApp("/sources");
    expect(await screen.findByText(/Looking for/)).toHaveTextContent(
      "Looking for Data Analyst in US, across 6 ready sources.",
    );
    await user.click(screen.getByRole("button", { name: "Search now" }));
    await waitFor(() => {
      expect(started).toBe(true);
    });

    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({ id: "s1", kind: "scrape", progress: 0.5, message: "Greenhouse: 12 new" }),
      );
    });
    const searching = screen.getByRole("button", { name: "Searching…" });
    expect(searching).toBeDisabled();
    const panel = searching.closest<HTMLElement>("[data-slot=card]");
    if (!panel) throw new Error("no search panel");
    expect(within(panel).getByRole("progressbar", { name: "Search progress" })).toBeVisible();
    expect(within(panel).getByText("Greenhouse: 12 new")).toBeVisible(); // also in the tray

    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({ id: "s1", kind: "scrape", status: "succeeded", progress: 1 }),
      );
    });
    expect(await screen.findByText(/Last search/)).toHaveTextContent(
      "14 new jobs, 28 already seen, 3,462 that no longer match your targets removed",
    );
    expect(screen.getByRole("link", { name: "Review in Discover" })).toHaveAttribute(
      "href",
      "/discover",
    );
    await user.click(screen.getByText("Results by source"));
    expect(screen.getByText("gone: not found on this ATS")).toBeVisible();
    expect(screen.getByText(/skipped: needs an app ID/)).toBeVisible();
  });
});

describe("Company watchlist", () => {
  it("filters by board from a card and by name", async () => {
    const { user } = await renderApp("/sources");
    const list = await screen.findByRole("list", { name: "Companies" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);

    await user.click(within(card("Lever")).getByRole("button", { name: "16 companies" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(list).toHaveTextContent("Palantir");

    await user.click(screen.getByRole("combobox", { name: "Job board" }));
    await user.click(screen.getByRole("option", { name: "All boards" }));
    await user.type(screen.getByLabelText("Find a company"), "travel");
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(list).toHaveTextContent("Airbnb");
  });

  it("checks pasted boards and adds the ones that exist", async () => {
    const checked: unknown[] = [];
    let added: unknown = null;
    server.use(
      http.post("/api/companies/check", async ({ request }) => {
        const body = (await request.json()) as { ats: string; slug: string };
        checked.push(body);
        return HttpResponse.json(
          body.slug === "stripe"
            ? { ok: true, jobs: 312, company: "Stripe", detail: null }
            : {
                ok: false,
                jobs: 0,
                company: null,
                detail: "No job board with that name on this ATS.",
              },
        );
      }),
      http.post("/api/companies", async ({ request }) => {
        added = await request.json();
        return HttpResponse.json(
          [company({ id: 9, slug: "stripe", name: "Stripe", source: "user" })],
          { status: 201 },
        );
      }),
    );
    const { user } = await renderApp("/sources");
    const form = await screen.findByRole("form", { name: "Add companies" });
    await user.type(
      within(form).getByLabelText("Add companies"),
      "https://boards.greenhouse.io/stripe{enter}nope-co{enter}https://example.com/jobs",
    );
    await user.click(within(form).getByRole("button", { name: "Check and add" }));

    expect(await within(form).findByText(/Stripe: 312 open jobs/)).toBeInTheDocument();
    expect(within(form).getByText(/No job board with that name/)).toBeInTheDocument();
    expect(
      within(form).getByText("Not a board link or name: https://example.com/jobs"),
    ).toBeInTheDocument();
    expect(checked).toHaveLength(2);
    expect(checked).toContainEqual({ ats: "greenhouse", slug: "nope-co" });
    expect(added).toEqual({ ats: "greenhouse", companies: [{ slug: "stripe", name: "Stripe" }] });
  });

  it("removes companies you added and switches off starter ones", async () => {
    let removed = false;
    let patched: unknown = null;
    server.use(
      http.get("/api/companies", () =>
        HttpResponse.json(
          removed
            ? [company()]
            : [company(), company({ id: 5, slug: "my-co", name: "My Co", source: "user" })],
        ),
      ),
      http.delete("/api/companies/5", () => {
        removed = true;
        return new HttpResponse(null, { status: 204 });
      }),
      http.patch("/api/companies/1", async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json(company({ enabled: false }));
      }),
    );
    const { user } = await renderApp("/sources");
    const list = await screen.findByRole("list", { name: "Companies" });
    expect(within(list).queryByRole("button", { name: "Remove Airbnb" })).not.toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Remove My Co" }));
    await waitFor(() => {
      expect(within(list).queryByText("My Co")).not.toBeInTheDocument();
    });
    await user.click(within(list).getByRole("switch", { name: "Airbnb" }));
    await waitFor(() => {
      expect(patched).toEqual({ enabled: false });
    });
  });
});
