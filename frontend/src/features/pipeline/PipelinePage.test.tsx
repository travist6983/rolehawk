import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { moveCard, type Stage } from "@/api/queries";
import { applicationDetail, board, boardCard } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

import { daysText, stageForColumn } from "./pipelineText";

const cards = [
  boardCard(),
  boardCard({
    application_id: 8,
    title: "Data Engineer",
    company: "Globex",
    stage: "applied",
    score: 64,
    days_in_stage: 9,
    next_action: "Send a follow-up",
  }),
  boardCard({
    application_id: 9,
    title: "Analyst",
    company: "Initech",
    stage: "saved",
    score: null,
    has_documents: false,
    next_action: "Write your application",
    flags: 0,
  }),
];

/** A board that remembers moves, like the real API. */
function withBoard() {
  const patches: { id: string; body: unknown }[] = [];
  let current = board(cards);
  server.use(
    http.get("/api/pipeline", () => HttpResponse.json(current)),
    http.patch("/api/applications/:id", async ({ request, params }) => {
      const body = (await request.json()) as { stage: Stage };
      patches.push({ id: String(params.id), body });
      current = moveCard(current, Number(params.id), body.stage);
      return HttpResponse.json(applicationDetail());
    }),
  );
  return patches;
}

function column(name: string): HTMLElement {
  return screen.getByRole("region", { name: new RegExp(`^${name}`) });
}

describe("Pipeline board", () => {
  it("shows a column per stage with card details", async () => {
    withBoard();
    await renderApp("/");
    const pipeline = await screen.findByRole("list", { name: "Pipeline" });
    const headings = within(pipeline).getAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual([
      "Saved1",
      "Applying1",
      "Applied1",
      "Screen0",
      "Interview0",
      "Offer0",
      "Closed0",
    ]);
    const applied = within(column("Applied")).getByRole("article");
    expect(applied).toHaveTextContent("Globex");
    expect(applied).toHaveTextContent("9 days in stage");
    expect(applied).toHaveTextContent("Send a follow-up");
    expect(within(applied).getByLabelText("Fit score 64 out of 100")).toBeVisible();
    expect(within(applied).getByRole("link", { name: "Data Engineer" })).toHaveAttribute(
      "href",
      "/applications/8",
    );
  });

  it("moves a card with the keyboard and announces each step", async () => {
    const patches = withBoard();
    await renderApp("/");
    const target = await screen.findByRole("article", { name: /^Senior Data Analyst at/ });
    target.focus();
    fireEvent.keyDown(target, { key: " " });
    expect(screen.getByText(/Picked up Senior Data Analyst/)).toBeInTheDocument();
    fireEvent.keyDown(target, { key: "ArrowRight" });
    expect(screen.getByText("Over Applied.")).toBeInTheDocument();
    fireEvent.keyDown(target, { key: " " });

    await waitFor(() => {
      expect(patches).toEqual([{ id: "7", body: { stage: "applied" } }]);
    });
    expect(within(column("Applied")).getAllByRole("article")).toHaveLength(2);
    expect(screen.getByText("Moved Senior Data Analyst to Applied.")).toBeInTheDocument();
  });

  it("cancels a keyboard move with Escape", async () => {
    const patches = withBoard();
    await renderApp("/");
    const target = await screen.findByRole("article", { name: /^Analyst at/ });
    fireEvent.keyDown(target, { key: " " });
    fireEvent.keyDown(target, { key: "ArrowRight" });
    fireEvent.keyDown(target, { key: "Escape" });
    expect(screen.getByText("Cancelled. Analyst stayed in Saved.")).toBeInTheDocument();
    expect(patches).toEqual([]);
  });

  it("asks how an application closed", async () => {
    const patches = withBoard();
    const { user } = await renderApp("/");
    const target = await screen.findByRole("article", { name: /^Data Engineer at/ });
    fireEvent.keyDown(target, { key: " " });
    for (let i = 0; i < 6; i++) fireEvent.keyDown(target, { key: "ArrowRight" });
    expect(screen.getByText("Over Closed.")).toBeInTheDocument();
    fireEvent.keyDown(target, { key: "Enter" });
    const dialog = await screen.findByRole("dialog", { name: "Close this application" });
    await user.click(within(dialog).getByRole("button", { name: "Ghosted" }));
    await waitFor(() => {
      expect(patches).toEqual([{ id: "8", body: { stage: "ghosted" } }]);
    });
  });

  it("moves a card from its menu and rolls back if the server refuses", async () => {
    server.use(
      http.get("/api/pipeline", () => HttpResponse.json(board(cards))),
      http.patch("/api/applications/:id", () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 }),
      ),
    );
    const { user } = await renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Move Analyst at Initech" }));
    await user.click(await screen.findByRole("menuitem", { name: "Interview" }));
    await waitFor(() => {
      expect(within(column("Saved")).getByRole("article")).toHaveTextContent("Analyst");
    });
  });

  it("opens the application with Enter", async () => {
    withBoard();
    server.use(http.get("/api/applications/7", () => HttpResponse.json(applicationDetail())));
    await renderApp("/");
    fireEvent.keyDown(await screen.findByRole("article", { name: /^Senior Data Analyst at/ }), {
      key: "Enter",
    });
    expect(
      await screen.findByRole("heading", { name: "Senior Data Analyst", level: 1 }),
    ).toBeVisible();
  });
});

describe("pipeline helpers", () => {
  it("moves cards between columns", () => {
    const moved = moveCard(board(cards), 9, "rejected");
    const closed = moved.columns.find((c) => c.id === "closed");
    expect(closed?.cards.map((c) => [c.application_id, c.stage, c.days_in_stage])).toEqual([
      [9, "rejected", 0],
    ]);
    expect(moved.columns.find((c) => c.id === "saved")?.cards).toEqual([]);
    expect(moveCard(board(cards), 999, "offer")).toEqual(board(cards));
  });

  it("maps columns to stages", () => {
    expect(stageForColumn(board(), "screen")).toBe("screen");
    expect(stageForColumn(board(), "closed")).toBeNull();
    expect(daysText(0)).toBe("today");
    expect(daysText(1)).toBe("1 day");
  });
});
