import { act, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { FakeEventSource } from "@/test/fakeEventSource";
import {
  emptyPreferences,
  interviewState,
  llmStatus,
  profileOverview,
  question,
  sampleProfile,
  searchTarget,
  task,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

describe("Onboarding", () => {
  it("starts at Connect Claude when no key is set, and allows the Claude Code path", async () => {
    server.use(
      http.get("/api/llm/status", () =>
        HttpResponse.json(llmStatus({ configured: false, key_source: "none" })),
      ),
    );
    const { user } = await renderApp("/onboarding");
    expect(await screen.findByText("Claude connection")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Connect Claude");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /Claude Code instead/ }));
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Questions");
  });

  it("answers single-choice questions with one click and shows the next question", async () => {
    let sent: unknown;
    server.use(
      http.post("/api/setup/interview/answer", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(
          interviewState({
            answered: 3,
            remaining: 5,
            question: question({
              id: "prefs.salary",
              prompt: "What's the lowest salary you'd accept?",
              kind: "text",
              choices: [],
              optional: true,
              placeholder: "e.g. 120k USD",
            }),
          }),
        );
      }),
    );
    const { user } = await renderApp("/onboarding?step=interview");
    expect(
      await screen.findByRole("heading", { name: "How do you want to work?" }),
    ).toBeInTheDocument();
    expect(screen.getByText("2 answered · about 6 to go")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Skip" })).not.toBeInTheDocument(); // required

    await user.click(screen.getByRole("button", { name: "Hybrid" }));
    expect(sent).toEqual({ question_id: "prefs.remote", value: "hybrid" });
    expect(
      await screen.findByRole("heading", { name: "What's the lowest salary you'd accept?" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skip" })).toBeInTheDocument();
  });

  it("submits forms and shows the backend's validation message", async () => {
    server.use(
      http.get("/api/setup/interview", () =>
        HttpResponse.json(
          interviewState({
            question: question({
              id: "role.add",
              prompt: "Tell me about your most recent role.",
              kind: "form",
              choices: [],
              optional: true,
              skip_label: "I don't have work experience yet",
              fields: [
                {
                  name: "title",
                  label: "Job title",
                  kind: "text",
                  required: true,
                  placeholder: null,
                },
                { name: "dates", label: "Dates", kind: "text", required: false, placeholder: null },
              ],
            }),
          }),
        ),
      ),
      http.post("/api/setup/interview/answer", () =>
        HttpResponse.json({ detail: "Couldn't read those dates." }, { status: 422 }),
      ),
    );
    const { user } = await renderApp("/onboarding?step=interview");
    const submit = await screen.findByRole("button", { name: "Continue" });
    expect(submit).toBeDisabled(); // title is required
    await user.type(screen.getByLabelText(/Job title/), "Data Analyst");
    await user.type(screen.getByLabelText("Dates"), "a while ago");
    await user.click(submit);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't read those dates.");
    expect(screen.getByRole("button", { name: "I don't have work experience yet" })).toBeEnabled();
  });

  it("celebrates when the interview is complete", async () => {
    server.use(
      http.get("/api/setup/interview", () =>
        HttpResponse.json(interviewState({ question: null, remaining: 0, complete: true })),
      ),
      http.get("/api/profile", () =>
        HttpResponse.json(
          profileOverview({
            search_targets: [
              {
                id: 1,
                title: "Data Analyst",
                seniority: null,
                locations: ["Denver"],
                remote_policy: "hybrid",
                country: "US",
                salary_min: 95000,
                active: true,
              },
            ],
          }),
        ),
      ),
    );
    const { user } = await renderApp("/onboarding?step=interview");
    await user.click(await screen.findByRole("button", { name: "Continue" }));
    expect(screen.getByRole("list", { name: "Search targets" })).toHaveTextContent("Data Analyst");
    await user.click(screen.getByRole("button", { name: "Finish setup" }));
    expect(await screen.findByRole("heading", { name: "Profile", level: 1 })).toBeInTheDocument();
  });

  it("ends by starting the first search and opening Sources", async () => {
    let started = false;
    server.use(
      http.get("/api/profile", () =>
        HttpResponse.json(profileOverview({ search_targets: [searchTarget()] })),
      ),
      http.post("/api/scrape", () => {
        started = true;
        return HttpResponse.json({ task_id: "s1" }, { status: 202 });
      }),
    );
    const { user } = await renderApp("/onboarding?step=sources");
    expect(await screen.findByText("6 job sources are ready")).toBeInTheDocument();
    expect(screen.getByText(/starter watchlist of 114 companies/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Search now" }));
    expect(await screen.findByRole("heading", { name: "Sources", level: 1 })).toBeInTheDocument();
    expect(started).toBe(true);
  });

  it("uploads a resume, follows extraction live, and saves the reviewed draft", async () => {
    let uploadedContent: string | null = null;
    let applied: { profile: { skills: string[] } } | null = null;
    let draftReady = false;
    server.use(
      http.post("/api/setup/documents", async ({ request }) => {
        const file = (await request.formData()).get("file");
        // jsdom's FormData loses the filename on its way into Node's fetch, so check the
        // content (browsers keep the name; covered by the end-to-end check).
        uploadedContent = typeof file === "object" && file !== null ? await file.text() : null;
        return HttpResponse.json(
          {
            id: 4,
            filename: "cv.pdf",
            kind: "pdf",
            size: 1234,
            chars: 900,
            created_at: "2026-10-31T12:00:00Z",
          },
          { status: 201 },
        );
      }),
      http.post("/api/setup/extract", () => HttpResponse.json({ task_id: "x1" }, { status: 202 })),
      http.get("/api/setup/draft", () =>
        draftReady
          ? HttpResponse.json({
              profile: sampleProfile(),
              preferences: emptyPreferences(),
              document_ids: [4],
              document_conflicts: [],
              conflicts: [],
              created_at: "2026-10-31T12:01:00Z",
            })
          : HttpResponse.json({ detail: "No setup draft" }, { status: 404 }),
      ),
      http.post("/api/setup/draft/apply", async ({ request }) => {
        applied = (await request.json()) as typeof applied;
        draftReady = false;
        return HttpResponse.json({
          profile: sampleProfile(),
          preferences: emptyPreferences(),
          added: { experience: 1, skills: 2 },
          updated: {},
          completeness: { score: 50, missing: [] },
        });
      }),
    );
    const { user } = await renderApp("/onboarding?step=resume");
    await screen.findByText("Drop your resume or LinkedIn export here");

    const file = new File(["%PDF-1.4 fake"], "cv.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Choose resume files"), file);
    expect(await screen.findByText("cv.pdf")).toBeInTheDocument();
    expect(uploadedContent).toBe("%PDF-1.4 fake");

    await user.click(screen.getByRole("button", { name: /Read with Claude/ }));
    await screen.findByText("queued");
    draftReady = true;
    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({ id: "x1", kind: "setup-extract", status: "succeeded" }),
      );
    });

    expect(await screen.findByText("Check every line.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Ada Example")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove skill Accessibility" }));
    await user.click(screen.getByRole("button", { name: "Save to profile" }));

    await waitFor(() => {
      expect(applied?.profile.skills).toEqual(["TypeScript", "React"]);
    });
    // The step changes only after the save response; wait for it (findBy would match the old step).
    await waitFor(() => {
      expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Questions");
    });
  });

  it("asks which version is right when documents disagree", async () => {
    let applied: { resolutions?: Record<string, number> } | null = null;
    const conflict = {
      id: "c1",
      kind: "title" as const,
      subject: "Your role at Northwind Payments",
      question: "Is this the same role? Pick the title that's right.",
      options: [
        {
          label: "Senior Frontend Engineer",
          source: "LinkedIn export",
          patch: { kind: "role" as const, company: "", titles: [], institution: "", values: {} },
        },
        {
          label: "Lead Frontend Engineer",
          source: "cv.pdf",
          patch: { kind: "role" as const, company: "", titles: [], institution: "", values: {} },
        },
      ],
    };
    server.use(
      http.get("/api/setup/draft", () =>
        HttpResponse.json({
          profile: sampleProfile(),
          preferences: emptyPreferences(),
          document_ids: [4],
          document_conflicts: [conflict],
          conflicts: [conflict],
          created_at: "2026-10-31T12:01:00Z",
        }),
      ),
      http.post("/api/setup/draft/apply", async ({ request }) => {
        applied = (await request.json()) as typeof applied;
        return HttpResponse.json({
          profile: sampleProfile(),
          preferences: emptyPreferences(),
          added: {},
          updated: { experience: 1 },
          resolved: 1,
          completeness: { score: 50, missing: [] },
        });
      }),
    );
    const { user } = await renderApp("/onboarding?step=resume");
    expect(await screen.findByText("1 thing your documents disagree on")).toBeVisible();
    const save = screen.getByRole("button", { name: "Save to profile" });
    expect(save).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: /Lead Frontend Engineer/ }));
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => {
      expect(applied?.resolutions).toEqual({ c1: 1 });
    });
  });

  it("shows why extraction failed", async () => {
    server.use(
      http.post("/api/setup/documents/text", () =>
        HttpResponse.json(
          {
            id: 5,
            filename: "pasted-cv.txt",
            kind: "text",
            size: 10,
            chars: 10,
            created_at: "2026-10-31T12:00:00Z",
          },
          { status: 201 },
        ),
      ),
      http.post("/api/setup/extract", () => HttpResponse.json({ task_id: "x2" }, { status: 202 })),
    );
    const { user } = await renderApp("/onboarding?step=resume");
    await user.click(await screen.findByText("Or paste your CV text"));
    await user.type(screen.getByLabelText("CV text"), "Ada Example, engineer");
    await user.click(screen.getByRole("button", { name: "Use this text" }));
    await user.click(await screen.findByRole("button", { name: /Read with Claude/ }));
    await screen.findByText("queued");
    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({ id: "x2", status: "failed", error: "Claude is busy or unreachable right now." }),
      );
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Claude is busy");
    expect(screen.getByRole("button", { name: /Read with Claude/ })).toBeEnabled();
  });
});
