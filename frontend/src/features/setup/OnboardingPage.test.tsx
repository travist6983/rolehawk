import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { FakeEventSource } from "@/test/fakeEventSource";
import {
  badKey,
  emptyPreferences,
  interviewState,
  keyConnect,
  keyTest,
  llmStatus,
  noCredit,
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
    expect(await screen.findByText("Get your key (about 5 minutes)")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Connect Claude");
    expect(screen.getByRole("button", { name: /Connect/ })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /Claude Code instead/ }));
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Questions");
  });

  it("walks through getting a key, then saves it with a monthly limit", async () => {
    let configured = false;
    let key: unknown = null;
    let settings: unknown = null;
    server.use(
      http.get("/api/llm/status", () =>
        HttpResponse.json(
          llmStatus(
            configured
              ? { configured: true, key_source: "keychain", monthly_cap_usd: 50 }
              : { configured: false, key_source: "none", monthly_cap_usd: null },
          ),
        ),
      ),
      http.put("/api/llm/key", async ({ request }) => {
        key = await request.json();
        configured = true;
        return HttpResponse.json(keyConnect());
      }),
      http.patch("/api/llm/settings", async ({ request }) => {
        settings = await request.json();
        return HttpResponse.json(llmStatus({ configured: true, monthly_cap_usd: 50 }));
      }),
    );
    const { user } = await renderApp("/onboarding");
    expect(await screen.findByText(/Typical cost: about \$18 a month/)).toBeInTheDocument();
    expect(screen.getByText(/Writing and chat use Claude Opus 5.5/)).toBeInTheDocument();
    const steps = await screen.findByRole("list", { name: "Steps to connect Claude" });
    expect(within(steps).getByRole("link", { name: /Open API keys/ })).toHaveAttribute(
      "href",
      "https://platform.claude.com/settings/keys",
    );
    expect(within(steps).getByRole("link", { name: /Open Billing/ })).toHaveAttribute(
      "href",
      "https://platform.claude.com/settings/billing",
    );
    expect(screen.getByRole("radio", { name: "$25 a month" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(screen.getByRole("radio", { name: "$50 a month" }));
    await user.type(screen.getByLabelText("Your API key"), "sk-ant-test-1234567890");
    await user.click(screen.getByRole("button", { name: /Connect and test/ }));
    await waitFor(() => {
      expect(key).toEqual({ api_key: "sk-ant-test-1234567890" });
    });
    await waitFor(() => {
      expect(settings).toEqual({ monthly_cap_usd: 50 });
    });
    await waitFor(() => {
      expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Resume");
    });
  });

  it("shows pictures of the Claude Platform, marked as illustrations", async () => {
    server.use(
      http.get("/api/llm/status", () =>
        HttpResponse.json(llmStatus({ configured: false, key_source: "none" })),
      ),
    );
    const { user } = await renderApp("/onboarding");
    const steps = await screen.findByRole("list", { name: "Steps to connect Claude" });
    expect(within(steps).queryByRole("figure")).not.toBeInTheDocument();
    const toggles = within(steps).getAllByRole("button", { name: "Show me what this looks like" });
    expect(toggles).toHaveLength(3);
    const [, , keysToggle] = toggles;
    if (!keysToggle) throw new Error("missing toggle");
    await user.click(keysToggle);
    const figure = within(steps).getByRole("figure");
    expect(figure).toHaveTextContent(/Create key opens a short form/);
    expect(figure).toHaveTextContent(/Illustration only/);
    expect(within(steps).getByRole("button", { name: "Hide the picture" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("keeps a rejected key out and says how to fix it", async () => {
    server.use(
      http.get("/api/llm/status", () =>
        HttpResponse.json(llmStatus({ configured: false, key_source: "none" })),
      ),
      http.put("/api/llm/key", () => HttpResponse.json(keyConnect(badKey()))),
    );
    const { user } = await renderApp("/onboarding");
    await user.type(await screen.findByLabelText("Your API key"), "sk-ant-wrong-1234567890");
    await user.click(screen.getByRole("button", { name: /Connect and test/ }));
    const result = await screen.findByRole("status", { name: "Key test" });
    expect(result).toHaveTextContent("Anthropic didn't accept this key");
    expect(within(result).getByRole("link", { name: /Open API keys/ })).toHaveAttribute(
      "href",
      "https://platform.claude.com/settings/keys",
    );
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Connect Claude");
    expect(screen.getByLabelText("Your API key")).toHaveValue("sk-ant-wrong-1234567890");
  });

  it("saves a key with no credit, points to Billing, and tests again", async () => {
    let configured = false;
    let tests = 0;
    server.use(
      http.get("/api/llm/status", () =>
        HttpResponse.json(llmStatus(configured ? {} : { configured: false, key_source: "none" })),
      ),
      http.put("/api/llm/key", () => {
        configured = true;
        return HttpResponse.json(keyConnect(noCredit()));
      }),
      http.patch("/api/llm/settings", () => HttpResponse.json(llmStatus({ monthly_cap_usd: 25 }))),
      http.post("/api/llm/key/test", async ({ request }) => {
        tests += 1;
        expect(await request.json()).toEqual({});
        return HttpResponse.json(keyTest());
      }),
    );
    const { user } = await renderApp("/onboarding");
    await user.type(await screen.findByLabelText("Your API key"), "sk-ant-test-1234567890");
    await user.click(screen.getByRole("button", { name: /Connect and test/ }));
    const result = await screen.findByRole("status", { name: "Key test" });
    expect(result).toHaveTextContent("Your key works, but the account has no credit");
    expect(within(result).getByRole("link", { name: /Open Billing/ })).toHaveAttribute(
      "href",
      "https://platform.claude.com/settings/billing",
    );
    expect(await screen.findByText("Claude is connected.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue anyway" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Test again/ }));
    await waitFor(() => {
      expect(screen.getByRole("status", { name: "Key test" })).toHaveTextContent("Your key works");
    });
    expect(tests).toBe(1);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Resume");
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

  it("collects links as a list with add and remove buttons", async () => {
    let sent: unknown = null;
    server.use(
      http.get("/api/setup/interview", () =>
        HttpResponse.json(
          interviewState({
            question: question({
              id: "basics.contact",
              prompt: "How should employers reach you?",
              kind: "form",
              choices: [],
              fields: [
                {
                  name: "name",
                  label: "Full name",
                  kind: "text",
                  required: true,
                  placeholder: null,
                },
                {
                  name: "links",
                  label: "Links (LinkedIn, GitHub, site)",
                  kind: "list",
                  required: false,
                  placeholder: "https://www.linkedin.com/in/you",
                },
              ],
            }),
          }),
        ),
      ),
      http.post("/api/setup/interview/answer", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ detail: "stop here" }, { status: 422 });
      }),
    );
    const { user } = await renderApp("/onboarding?step=interview");
    await user.type(await screen.findByLabelText(/Full name/), "Ada Example");
    await user.type(
      screen.getByRole("textbox", { name: "Links (LinkedIn, GitHub, site)" }),
      "github.com/ada",
    );
    expect(screen.queryByRole("button", { name: /Remove link/ })).not.toBeInTheDocument();

    const add = screen.getByRole("button", { name: "Add another link" });
    await user.click(add);
    await user.type(screen.getByLabelText("Link 2"), "example.com/wrong");
    await user.click(add);
    await user.type(screen.getByLabelText("Link 3"), "ada.example.com");
    await user.click(add); // left empty: not sent
    await user.click(screen.getByRole("button", { name: "Remove link 2" }));
    expect(screen.getByLabelText("Link 2")).toHaveValue("ada.example.com");

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("stop here");
    expect(sent).toEqual({
      question_id: "basics.contact",
      value: { name: "Ada Example", links: ["github.com/ada", "ada.example.com"] },
    });
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
