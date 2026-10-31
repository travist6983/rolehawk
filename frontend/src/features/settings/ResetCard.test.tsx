import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "@/test/render";
import { server } from "@/test/server";

describe("Reset", () => {
  it("needs the scope typed, backs up, then reports what it removed", async () => {
    let body: unknown = null;
    server.use(
      http.post("/api/reset", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          scope: "jobs",
          backup: "/Users/ada/Offerbound/backups/offerbound-20261031-reset-jobs.zip",
          removed: { "job scores": 40, jobs: 2500 },
        });
      }),
    );
    const { user } = await renderApp("/settings");
    const group = await screen.findByRole("group", { name: "What to reset" });
    await user.click(await within(group).findByRole("radio", { name: /Jobs and scores/ }));

    const button = screen.getByRole("button", { name: "Reset jobs and scores" });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText(/to confirm/), "job");
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText(/to confirm/), "s");
    expect(button).toBeEnabled();
    await user.click(button);

    await waitFor(() => {
      expect(body).toEqual({ scope: "jobs", confirm: "jobs" });
    });
    const status = await screen.findByText("Reset done.");
    const summary = status.closest("[role=status]");
    expect(summary).toHaveTextContent("Removed 40 job scores, 2500 jobs.");
    expect(summary).toHaveTextContent("offerbound-20261031-reset-jobs.zip");
  });
});
