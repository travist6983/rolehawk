import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { llmStatus } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

describe("App shell", () => {
  it("renders the nav and the teaching empty pipeline", async () => {
    await renderApp();
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const label of ["Pipeline", "Discover", "Profile", "Sources", "Insights", "Settings"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(await screen.findByRole("heading", { name: "No applications yet" })).toBeInTheDocument();
    expect(screen.getAllByText(/^Step \d$/)).toHaveLength(3);
    expect(screen.getByRole("link", { name: "Choose sources" })).toHaveAttribute(
      "href",
      "/sources",
    );
  });

  it("navigates between screens and marks the current link", async () => {
    const { user } = await renderApp();
    const nav = screen.getByRole("navigation", { name: "Main" });
    await user.click(within(nav).getByRole("link", { name: "Discover" }));
    expect(
      await screen.findByRole("heading", { name: "No jobs to review yet" }),
    ).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Discover" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("switches theme and remembers it", async () => {
    const { user } = await renderApp();
    const nav = screen.getByRole("navigation", { name: "Main" });
    const theme = within(nav).getByRole("group", { name: "Theme" });
    await user.click(within(theme).getByRole("button", { name: "Dark" }));
    expect(within(theme).getByRole("button", { name: "Dark" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("rolehawk.theme")).toBe("dark");
  });

  it("asks to relaunch when the session can't be established", async () => {
    server.use(
      http.get("/api/session", () => HttpResponse.json({ detail: "no" }, { status: 401 })),
    );
    const { render } = await import("@testing-library/react");
    const { MemoryRouter } = await import("react-router");
    const { QueryClientProvider } = await import("@tanstack/react-query");
    const { App } = await import("@/App");
    const { testQueryClient } = await import("@/test/render");
    render(
      <QueryClientProvider client={testQueryClient()}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      await screen.findByRole("heading", { name: "Open RoleHawk from its launcher" }),
    ).toBeInTheDocument();
  });
});

describe("Settings", () => {
  it("saves an API key through the keychain endpoint without echoing it", async () => {
    let sentKey = "";
    server.use(
      http.get("/api/llm/status", () =>
        HttpResponse.json(llmStatus({ configured: false, key_source: "none" })),
      ),
      http.put("/api/llm/key", async ({ request }) => {
        sentKey = ((await request.json()) as { api_key: string }).api_key;
        return HttpResponse.json(llmStatus());
      }),
    );
    const { user } = await renderApp("/settings");
    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    const field = screen.getByLabelText("Anthropic API key");
    expect(field).toHaveAttribute("type", "password");
    await user.type(field, "sk-ant-api03-test-key");
    await user.click(screen.getByRole("button", { name: /Save and test/ }));
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(sentKey).toBe("sk-ant-api03-test-key");
    expect(screen.getByLabelText("Replace API key")).toHaveValue("");
  });

  it("shows routing and toggles smart routing", async () => {
    let patched: unknown;
    server.use(
      http.patch("/api/llm/settings", async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json(llmStatus({ smart_routing: false }));
      }),
    );
    const { user } = await renderApp("/settings");
    expect(
      await screen.findByRole("row", { name: /Ranking jobs claude-haiku-5-5/ }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("switch", { name: "Smart routing" }));
    expect(patched).toEqual({ smart_routing: false });
    expect(await screen.findByRole("switch", { name: "Smart routing" })).not.toBeChecked();
  });
});
