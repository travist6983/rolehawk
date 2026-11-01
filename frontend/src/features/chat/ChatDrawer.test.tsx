import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { FakeEventSource } from "@/test/fakeEventSource";
import { proposal, task } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server, sseResponse } from "@/test/server";

function drawer() {
  return screen.getByTestId("chat-drawer"); // aria-hidden while closed, so no accessible name
}

function chatHandlers(events: [string, unknown][], onMessage?: (body: unknown) => void) {
  return [
    http.post("/api/chat/sessions", () =>
      HttpResponse.json(
        {
          id: "s1",
          title: null,
          created_at: "2026-10-31T12:00:00Z",
          updated_at: "2026-10-31T12:00:00Z",
        },
        { status: 201 },
      ),
    ),
    http.post("/api/chat/sessions/:id/messages", async ({ request }) => {
      onMessage?.(await request.json());
      return sseResponse(events);
    }),
  ];
}

describe("ChatDrawer", () => {
  it("toggles with Cmd/Ctrl+K and closes with Escape, restoring focus", async () => {
    const { user } = await renderApp();
    expect(drawer()).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("dialog", { name: "Chat with Claude" })).not.toBeInTheDocument();

    const opener = screen.getByRole("button", { name: "Open chat" });
    opener.focus();
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("dialog", { name: "Chat with Claude" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Message" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(drawer()).toHaveAttribute("aria-hidden", "true");
    expect(opener).toHaveFocus();

    await user.keyboard("{Meta>}k{/Meta}");
    expect(drawer()).toHaveAttribute("aria-hidden", "false");
    await user.click(screen.getByRole("button", { name: "Close chat" }));
    expect(drawer()).toHaveAttribute("aria-hidden", "true");
  });

  it("shows a context chip for the current screen and sends it with the message", async () => {
    let sent: unknown;
    server.use(
      ...chatHandlers(
        [
          ["text", { text: "Sure." }],
          ["done", { message_id: 2 }],
        ],
        (body) => (sent = body),
      ),
    );
    const { user } = await renderApp("/settings");
    await user.click(screen.getByRole("button", { name: "Open chat" }));
    expect(within(drawer()).getByTestId("context-chip")).toHaveTextContent("Viewing: Settings");

    await user.type(
      screen.getByRole("combobox", { name: "Message" }),
      "Which model am I using?{Enter}",
    );
    await within(drawer()).findByText("Sure.");
    expect(sent).toMatchObject({
      text: "Which model am I using?",
      view: { label: "Settings", route: "/settings" },
    });
  });

  it("streams a reply with tool activity, cards, and memory proposals", async () => {
    server.use(
      ...chatHandlers([
        ["tool_call", { id: "c1", name: "query_pipeline", input: {} }],
        ["tool_result", { id: "c1", name: "query_pipeline", is_error: false }],
        ["text", { text: "You have " }],
        ["text", { text: "no applications yet." }],
        [
          "card",
          {
            card: {
              type: "job",
              job_id: 3,
              company: "Stripe",
              title: "Senior Frontend",
              score: 86,
            },
          },
        ],
        ["card", { card: { type: "mystery_card", value: 1 } }],
        ["done", { message_id: 2 }],
        ["memory_proposals", { proposals: [proposal()] }],
      ]),
    );
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Open chat" }));
    await user.type(screen.getByRole("combobox", { name: "Message" }), "How am I doing?{Enter}");

    const panel = drawer();
    expect(await within(panel).findByText("You have no applications yet.")).toBeInTheDocument();
    expect(within(panel).getByText("How am I doing?")).toBeInTheDocument();
    expect(within(panel).getByText("Checked your pipeline")).toBeInTheDocument();
    expect(within(panel).getByText("Senior Frontend")).toBeInTheDocument();
    expect(within(panel).getByLabelText("Fit score 86 out of 100")).toBeInTheDocument();
    expect(within(panel).getByText("mystery card")).toBeInTheDocument(); // registry fallback
    expect(await within(panel).findByText("Prefers async-first teams")).toBeInTheDocument();
    expect(localStorage.getItem("rolehawk.chatSession")).toBe("s1");
  });

  it("accepts a memory proposal from its chip", async () => {
    let accepted = 0;
    server.use(
      ...chatHandlers([
        ["text", { text: "Noted." }],
        ["card", { card: { type: "memory_proposal", proposal: proposal({ id: 9 }) } }],
        ["done", { message_id: 2 }],
      ]),
      http.post("/api/memory/proposals/:id/accept", ({ params }) => {
        accepted = Number(params.id);
        return HttpResponse.json(proposal({ id: 9, status: "accepted" }));
      }),
    );
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Open chat" }));
    await user.type(screen.getByRole("combobox", { name: "Message" }), "I like async teams{Enter}");
    await user.click(await within(drawer()).findByRole("button", { name: "Accept memory update" }));
    await waitFor(() => {
      expect(accepted).toBe(9);
    });
    expect(await within(drawer()).findByText("accepted")).toBeInTheDocument();
  });

  it("shows the backend's error message when Claude isn't connected", async () => {
    server.use(
      ...chatHandlers([
        [
          "error",
          {
            message: "Connect Claude in Settings (add an Anthropic API key) to use this feature.",
            kind: "LLMNotConfiguredError",
          },
        ],
      ]),
    );
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Open chat" }));
    await user.type(screen.getByRole("combobox", { name: "Message" }), "hi{Enter}");
    expect(await within(drawer()).findByRole("alert")).toHaveTextContent(
      "Connect Claude in Settings",
    );
  });

  it("runs slash commands directly and follows background tasks live", async () => {
    server.use(
      http.post("/api/commands/:name", ({ params }) =>
        params.name === "spend"
          ? HttpResponse.json({ task_id: null, result: { month_to_date_usd: 1.25 } })
          : HttpResponse.json({ task_id: "t9", result: null }),
      ),
    );
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Open chat" }));
    const input = screen.getByRole("combobox", { name: "Message" });

    await user.type(input, "/spend {Enter}");
    expect(await within(drawer()).findByText(/"month_to_date_usd": 1.25/)).toBeInTheDocument();

    await user.type(input, "/selftest {Enter}"); // with the menu open, Enter would pick the command
    await within(drawer()).findByText("queued");
    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({ id: "t9", status: "running", message: "Step 3 of 5" }),
      );
    });
    expect(within(drawer()).getByText("Step 3 of 5")).toBeInTheDocument();
    act(() => {
      FakeEventSource.latest().emit(
        "task.updated",
        task({ id: "t9", status: "succeeded", progress: 1 }),
      );
    });
    expect(await within(drawer()).findByText("succeeded")).toBeInTheDocument();
  });

  it("restores the previous conversation after a reload", async () => {
    localStorage.setItem("rolehawk.chatSession", "old");
    server.use(
      http.get("/api/chat/sessions/old/messages", () =>
        HttpResponse.json([
          {
            id: 1,
            session_id: "old",
            role: "user",
            content: "Earlier question",
            context: null,
            cards: [],
            created_at: "2026-10-30T10:00:00Z",
          },
          {
            id: 2,
            session_id: "old",
            role: "assistant",
            content: "Earlier answer",
            context: null,
            cards: [],
            created_at: "2026-10-30T10:00:01Z",
          },
        ]),
      ),
    );
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Open chat" }));
    expect(await within(drawer()).findByText("Earlier answer")).toBeInTheDocument();

    await user.click(within(drawer()).getByRole("button", { name: "New conversation" }));
    expect(within(drawer()).queryByText("Earlier answer")).not.toBeInTheDocument();
    expect(localStorage.getItem("rolehawk.chatSession")).toBeNull();
  });
});
