import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { FakeEventSource } from "@/test/fakeEventSource";
import {
  applicationDetail,
  applyPlan,
  bundle,
  jobDetail,
  jobPage,
  jobRow,
  task,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

import { flagsAt, linesToList, readOutcome, textToParagraphs } from "./applicationText";

function discoverWithJob() {
  server.use(
    http.get("/api/jobs", () => HttpResponse.json(jobPage([jobRow()], { ranked: 1 }))),
    http.get("/api/jobs/1", () => HttpResponse.json(jobDetail())),
  );
}

async function openApply() {
  const view = await renderApp("/discover");
  await view.user.click(await screen.findByRole("button", { name: "Senior Data Analyst" }));
  const sheet = await screen.findByRole("dialog");
  await view.user.click(await within(sheet).findByRole("button", { name: "Write application" }));
  const dialog = await screen.findByRole("dialog", { name: "Apply to this job" });
  return { ...view, dialog };
}

describe("Apply from Discover", () => {
  it("shows the fit and cost, runs /apply, then opens the application", async () => {
    discoverWithJob();
    let body: unknown = null;
    server.use(
      http.post("/api/apply/plan", () => HttpResponse.json(applyPlan())),
      http.post("/api/apply", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ task_id: "a1" }, { status: 202 });
      }),
      http.get("/api/applications/7", () => HttpResponse.json(applicationDetail())),
    );
    const { user, dialog } = await openApply();
    expect(await within(dialog).findByText(/Fit score/)).toBeVisible();
    expect(dialog).toHaveTextContent("your threshold is 60");
    expect(dialog).toHaveTextContent("Estimated cost: about $0.14.");

    await user.click(within(dialog).getByRole("button", { name: "Write CV and cover letter" }));
    await waitFor(() => {
      expect(body).toEqual({ job_id: 1, force: false });
    });
    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({ id: "a1", kind: "apply", progress: 0.2, message: "Writing your tailored CV" }),
      );
    });
    expect(within(dialog).getByRole("progressbar", { name: "Application progress" })).toBeVisible();
    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({
          id: "a1",
          kind: "apply",
          status: "succeeded",
          progress: 1,
          result: { status: "needs_review", application_id: 7, fit: applyPlan().fit, flags: [] },
        }),
      );
    });
    expect(
      await screen.findByRole("heading", { name: "Senior Data Analyst", level: 1 }),
    ).toBeVisible();
    expect(screen.getByRole("tab", { name: "Documents", selected: true })).toBeVisible();
  });

  it("explains a score below the threshold and can apply anyway", async () => {
    discoverWithJob();
    const bodies: unknown[] = [];
    server.use(
      http.post("/api/apply/plan", () => HttpResponse.json(applyPlan({ fit: null }))),
      http.post("/api/apply", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ task_id: `a${String(bodies.length)}` }, { status: 202 });
      }),
    );
    const { user, dialog } = await openApply();
    expect(await within(dialog).findByText(/Not ranked yet/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Write CV and cover letter" }));
    await waitFor(() => {
      expect(bodies).toHaveLength(1);
    });
    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({
          id: "a1",
          kind: "apply",
          status: "succeeded",
          result: {
            status: "below_threshold",
            application_id: null,
            fit: { score: 41, threshold: 60, reasons: ["Different field"], must_have_gaps: [] },
            flags: [],
          },
        }),
      );
    });
    expect(await within(dialog).findByText(/scored below your threshold/)).toBeVisible();
    expect(dialog).toHaveTextContent("Different field");
    await user.click(within(dialog).getByRole("button", { name: "Apply anyway" }));
    await waitFor(() => {
      expect(bodies[1]).toEqual({ job_id: 1, force: true });
    });
  });

  it("explains what's missing before it can run", async () => {
    discoverWithJob();
    server.use(
      http.post("/api/apply/plan", () => HttpResponse.json(applyPlan({ has_profile: false }))),
    );
    const { dialog } = await openApply();
    expect(await within(dialog).findByRole("link", { name: "Add it in Profile" })).toBeVisible();
    expect(
      within(dialog).getByRole("button", { name: "Write CV and cover letter" }),
    ).toBeDisabled();
  });
});

describe("Application page", () => {
  it("shows documents with flags in place and saves edits", async () => {
    let saved: unknown = null;
    server.use(
      http.get("/api/applications/7", () => HttpResponse.json(applicationDetail())),
      http.put("/api/applications/7/documents", async ({ request }) => {
        saved = await request.json();
        return HttpResponse.json(
          applicationDetail({
            documents: bundle({ flags: [], updated_at: "2026-10-31T12:05:00Z" }),
          }),
        );
      }),
    );
    const { user } = await renderApp("/applications/7");
    expect(await screen.findByText("1 line to check")).toBeVisible();
    const summary = screen.getByRole("region", { name: "Summary" });
    expect(summary).toHaveTextContent("300% isn't in your profile");
    expect(screen.getByTitle("CV PDF")).toHaveAttribute(
      "src",
      "/api/applications/7/files/cv.pdf?v=2026-10-31T12%3A00%3A00Z",
    );
    expect(screen.getByRole("link", { name: "Word" })).toHaveAttribute(
      "href",
      "/api/applications/7/files/cv.docx",
    );

    const save = screen.getByRole("button", { name: "Save and update files" });
    expect(save).toBeDisabled();
    const field = within(summary).getByLabelText("Summary");
    await user.clear(field);
    await user.type(field, "Analyst who builds revenue dashboards.");
    const bullets = screen.getByLabelText(/Data Analyst, Northwind/);
    await user.type(bullets, "{enter}Mentored two analysts");
    await user.click(save);
    await waitFor(() => {
      expect(saved).not.toBeNull();
    });
    const body = saved as { cv: { summary: string; experience: { bullets: string[] }[] } };
    expect(body.cv.summary).toBe("Analyst who builds revenue dashboards.");
    expect(body.cv.experience[0]?.bullets).toEqual([
      "Built the revenue dashboard",
      "Cut reporting time in half",
      "Mentored two analysts",
    ]);
    expect(await screen.findByTitle("CV PDF")).toHaveAttribute(
      "src",
      "/api/applications/7/files/cv.pdf?v=2026-10-31T12%3A05%3A00Z",
    );
    expect(screen.queryByText("1 line to check")).not.toBeInTheDocument();
  });

  it("shows requirements and the ATS check on the Checks tab", async () => {
    server.use(http.get("/api/applications/7", () => HttpResponse.json(applicationDetail())));
    const { user } = await renderApp("/applications/7");
    await user.click(await screen.findByRole("tab", { name: "Checks" }));
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("SQL");
    expect(rows[1]).toHaveTextContent("Matched");
    expect(rows[2]).toHaveTextContent("Not in your profile");
    expect(rows[2]).toHaveTextContent("Skipped");
    const ats = screen.getByRole("region", { name: "How an ATS reads your CV" });
    expect(ats).toHaveTextContent("Plain hyphens in dates (failed)");
    expect(ats).toHaveTextContent("Readable text (passed)");
  });

  it("keeps, softens, or drops a stretch", async () => {
    const stretch = {
      document: "cv" as const,
      location: "experience.0.bullets.1",
      text: "Cut reporting time in half",
      issue: "The profile says you helped; 'cut' claims it alone.",
      source: "review" as const,
      kind: "stretch" as const,
    };
    let kept: unknown = null;
    server.use(
      http.get("/api/applications/7", () =>
        HttpResponse.json(applicationDetail({ documents: bundle({ flags: [stretch] }) })),
      ),
      http.post("/api/applications/7/flags/keep", async ({ request }) => {
        kept = await request.json();
        return HttpResponse.json(applicationDetail({ documents: bundle({ flags: [] }) }));
      }),
    );
    const { user } = await renderApp("/applications/7");
    const flag = await screen.findByText(/Stretch:/);
    const item = flag.closest("li");
    if (!item) throw new Error("no flag item");

    await user.click(within(item).getByRole("button", { name: "Soften" }));
    expect(screen.getByLabelText("What should change? (optional)")).toHaveValue(
      `Soften this line so I can defend it in an interview: "Cut reporting time in half" (${stretch.issue})`,
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(within(item).getByRole("button", { name: "Drop line" }));
    expect(screen.getByLabelText(/Data Analyst, Northwind/)).toHaveValue(
      "Built the revenue dashboard",
    );
    expect(screen.getByRole("button", { name: "Save and update files" })).toBeEnabled();

    await user.click(within(item).getByRole("button", { name: "Keep as written" }));
    await waitFor(() => {
      expect(kept).toEqual({
        document: "cv",
        location: "experience.0.bullets.1",
        text: "Cut reporting time in half",
      });
    });
    await waitFor(() => {
      expect(screen.queryByText(/Stretch:/)).not.toBeInTheDocument();
    });
  });

  it("switches to the cover letter", async () => {
    server.use(http.get("/api/applications/7", () => HttpResponse.json(applicationDetail())));
    const { user } = await renderApp("/applications/7");
    await user.click(await screen.findByRole("button", { name: "Cover letter" }));
    expect(screen.getByLabelText(/Letter \(blank line/)).toHaveValue(
      "First paragraph.\n\nSecond paragraph.",
    );
    expect(screen.getByTitle("Cover letter PDF")).toBeVisible();
  });

  it("rewrites one section with an instruction", async () => {
    let body: unknown = null;
    server.use(
      http.get("/api/applications/7", () => HttpResponse.json(applicationDetail())),
      http.post("/api/applications/7/regenerate", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ task_id: "r1" }, { status: 202 });
      }),
    );
    const { user } = await renderApp("/applications/7");
    const skills = await screen.findByRole("region", { name: "Skills" });
    await user.click(within(skills).getByRole("button", { name: "Rewrite" }));
    await user.type(within(skills).getByLabelText(/What should change/), "Lead with Looker");
    await user.click(within(skills).getByRole("button", { name: "Rewrite with Claude" }));
    await waitFor(() => {
      expect(body).toEqual({ section: "skills", instruction: "Lead with Looker" });
    });
    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({ id: "r1", kind: "application-regenerate", message: "Rewriting the skills" }),
      );
    });
    expect(within(skills).getByRole("progressbar", { name: "Rewriting" })).toBeVisible();
  });

  it("autofills the form without submitting and marks it applied", async () => {
    let patched: unknown = null;
    server.use(
      http.get("/api/applications/7", () => HttpResponse.json(applicationDetail())),
      http.post("/api/applications/7/autofill", () =>
        HttpResponse.json({
          url: "https://job-boards.greenhouse.io/globex/jobs/1",
          ats: "greenhouse",
          filled: ["First Name", "Email"],
          attached: ["Resume/CV"],
          needs_you: ["Why Globex?"],
          note: null,
        }),
      ),
      http.patch("/api/applications/7", async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json(
          applicationDetail({ stage: "applied", applied_at: new Date().toISOString() }),
        );
      }),
    );
    const { user } = await renderApp("/applications/7");
    await user.click(await screen.findByRole("button", { name: "Autofill application" }));
    expect(await screen.findByText(/Nothing has been submitted/)).toBeVisible();
    expect(screen.getByText("Filled: First Name, Email")).toBeVisible();
    expect(screen.getByText(/Still needs you: Why Globex\?/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Mark as applied" }));
    await waitFor(() => {
      expect(patched).toEqual({ stage: "applied" });
    });
    expect(await screen.findByText(/Applied just now/)).toBeVisible();
  });

  it("says why Autofill waits while the documents are written", async () => {
    server.use(
      http.get("/api/applications/7", () =>
        HttpResponse.json(applicationDetail({ documents: null })),
      ),
    );
    await renderApp("/applications/7");
    expect(await screen.findByRole("button", { name: "Autofill application" })).toBeDisabled();
    expect(
      screen.getByText("Autofill is ready once the CV and cover letter are written."),
    ).toBeVisible();
  });

  it("shows the job and timeline tabs", async () => {
    server.use(http.get("/api/applications/7", () => HttpResponse.json(applicationDetail())));
    const { user } = await renderApp("/applications/7");
    await user.click(await screen.findByRole("tab", { name: "Job" }));
    expect(screen.getByText(/own reporting for our finance team/)).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Timeline" }));
    expect(screen.getByRole("list", { name: "Stage history" })).toHaveTextContent("Applying");
  });

  it("handles a missing application", async () => {
    server.use(
      http.get("/api/applications/99", () =>
        HttpResponse.json({ detail: "Unknown application" }, { status: 404 }),
      ),
    );
    await renderApp("/applications/99");
    expect(await screen.findByRole("heading", { name: "Application not found" })).toBeVisible();
  });
});

describe("application helpers", () => {
  it("parses editor text", () => {
    expect(linesToList("- one\n\n• two\n  three ")).toEqual(["one", "two", "three"]);
    expect(textToParagraphs("a\nb\n\n\nc")).toEqual(["a b", "c"]);
  });

  it("finds flags by location", () => {
    const flags = bundle().flags;
    expect(flagsAt(flags, "cv", "summary")).toHaveLength(1);
    expect(flagsAt(flags, "cv", "sum")).toHaveLength(0);
    expect(flagsAt(flags, "cover_letter", "summary")).toHaveLength(0);
  });

  it("reads task results defensively", () => {
    expect(
      readOutcome({ status: "ready", application_id: 3, fit: { score: 80 } })?.application_id,
    ).toBe(3);
    expect(readOutcome({ status: "weird" })).toBeNull();
    expect(readOutcome(null)).toBeNull();
  });
});
