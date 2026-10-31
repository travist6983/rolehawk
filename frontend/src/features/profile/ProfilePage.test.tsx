import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import {
  emptyPreferences,
  interviewState,
  memory,
  profileOverview,
  proposal,
  sampleProfile,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const filledMemory = memory({
  profile: "# Profile\n\n## Skills\n\n- TypeScript\n",
  preferences: "# Preferences\n\n## Remote\n\n- Remote only\n",
});

function filledOverview() {
  return profileOverview({
    profile: sampleProfile(),
    preferences: {
      ...emptyPreferences(),
      target_titles: ["Staff Engineer"],
      remote: "remote",
      salary_floor: { amount: 150000, currency: "USD", period: "year" },
    },
    completeness: { score: 63, missing: ["work authorization"] },
    search_targets: [
      {
        id: 1,
        title: "Staff Engineer",
        seniority: null,
        locations: [],
        remote_policy: "remote",
        country: "US",
        salary_min: 150000,
        active: true,
      },
    ],
  });
}

describe("ProfilePage", () => {
  it("teaches the next step when the profile is empty", async () => {
    server.use(
      http.get("/api/memory", () =>
        HttpResponse.json(memory({ profile: "# Profile\n", preferences: "# Preferences\n" })),
      ),
    );
    await renderApp("/profile");
    expect(
      await screen.findByRole("heading", { name: "Your profile is empty" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Import" })).toHaveAttribute(
      "href",
      "/onboarding?step=resume",
    );
    expect(screen.getByRole("link", { name: "Start questions" })).toHaveAttribute(
      "href",
      "/onboarding?step=interview",
    );
  });

  it("shows the parsed profile, preferences, targets, and completeness", async () => {
    server.use(
      http.get("/api/memory", () => HttpResponse.json(filledMemory)),
      http.get("/api/profile", () => HttpResponse.json(filledOverview())),
      http.get("/api/memory/proposals", () => HttpResponse.json([proposal()])),
    );
    await renderApp("/profile");

    expect(await screen.findByText("Profile 63% complete")).toBeInTheDocument();
    expect(screen.getByText("Missing: work authorization")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Continue setup/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Suggested updates (1)" })).toBeInTheDocument();
    expect(screen.getByText("Ada Example")).toBeInTheDocument();
    expect(
      screen.getByText("Led the checkout redesign, lifting conversion 12%"),
    ).toBeInTheDocument();
    expect(screen.getByText("Accessibility")).toBeInTheDocument();
    expect(screen.getByText("$150,000 per year")).toBeInTheDocument();
    expect(screen.getAllByText("Not set").length).toBeGreaterThan(0);
    const targets = screen.getByText("Search targets").closest<HTMLElement>('[data-slot="card"]');
    expect(targets).not.toBeNull();
    expect(within(targets ?? document.body).getByText("Staff Engineer")).toBeInTheDocument();
  });

  it("hides 'Continue setup' once the interview is complete", async () => {
    server.use(
      http.get("/api/memory", () => HttpResponse.json(filledMemory)),
      http.get("/api/profile", () => HttpResponse.json(filledOverview())),
      http.get("/api/setup/interview", () =>
        HttpResponse.json(interviewState({ question: null, remaining: 0, complete: true })),
      ),
    );
    await renderApp("/profile");
    await screen.findByText("Profile 63% complete");
    expect(screen.queryByRole("link", { name: /Continue setup/ })).not.toBeInTheDocument();
  });

  it("edits a memory file as markdown and saves it verbatim", async () => {
    let saved: unknown;
    server.use(
      http.get("/api/memory", () => HttpResponse.json(filledMemory)),
      http.get("/api/profile", () => HttpResponse.json(filledOverview())),
      http.put("/api/memory/:target", async ({ request, params }) => {
        saved = { target: params.target, ...((await request.json()) as object) };
        return HttpResponse.json(filledMemory);
      }),
    );
    const { user } = await renderApp("/profile");
    await user.click(await screen.findByRole("button", { name: "Edit preferences" }));
    const editor = screen.getByRole("textbox", { name: /Markdown/ });
    expect(editor).toHaveValue(filledMemory.preferences);
    await user.clear(editor);
    await user.type(editor, "## Remote{Enter}- Hybrid");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(saved).toEqual({ target: "preferences", markdown: "## Remote\n- Hybrid" });
    expect(await screen.findByRole("button", { name: "Edit preferences" })).toBeInTheDocument();
  });
});
