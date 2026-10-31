import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";

import { FakeEventSource, fakeFactory } from "@/test/fakeEventSource";
import { task } from "@/test/fixtures";
import { testQueryClient } from "@/test/render";
import { server } from "@/test/server";

import { EventStreamProvider, useEventStream } from "./EventStreamProvider";
import { ProgressTray } from "./ProgressTray";

function Probe() {
  const { status, tasks } = useEventStream();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <ul>
        {tasks.map((t) => (
          <li key={t.id}>{`${t.id}:${t.status}:${String(t.progress)}`}</li>
        ))}
      </ul>
    </div>
  );
}

function renderStream() {
  return render(
    <QueryClientProvider client={testQueryClient()}>
      <EventStreamProvider factory={fakeFactory}>
        <Probe />
        <ProgressTray />
      </EventStreamProvider>
    </QueryClientProvider>,
  );
}

describe("useEventStream", () => {
  it("connects to /api/events and tracks connection status", () => {
    renderStream();
    const source = FakeEventSource.latest();
    expect(source.url).toBe("/api/events");
    expect(screen.getByTestId("status")).toHaveTextContent("connecting");
    act(() => {
      source.open();
    });
    expect(screen.getByTestId("status")).toHaveTextContent("open");
    act(() => {
      source.fail();
    });
    expect(screen.getByTestId("status")).toHaveTextContent("reconnecting");
  });

  it("applies task.updated events and shows running tasks in the tray", () => {
    renderStream();
    const source = FakeEventSource.latest();
    act(() => {
      source.emit("task.updated", task({ progress: 0.4 }));
    });
    expect(screen.getByText("t1:running:0.4")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Running tasks" })).toHaveTextContent("Self-test");
    expect(screen.getByText("40%")).toBeInTheDocument();

    act(() => {
      source.emit("task.updated", task({ status: "succeeded", progress: 1 }));
    });
    expect(screen.getByText("t1:succeeded:1")).toBeInTheDocument();
    expect(screen.queryByText("40%")).not.toBeInTheDocument();
  });

  it("toasts when a task it saw running finishes or fails", () => {
    const success = vi.spyOn(toast, "success");
    const failure = vi.spyOn(toast, "error");
    renderStream();
    const source = FakeEventSource.latest();
    act(() => {
      source.emit("task.updated", task({ id: "a" }));
      source.emit("task.updated", task({ id: "a", status: "succeeded" }));
      source.emit("task.updated", task({ id: "b", kind: "rank" }));
      source.emit("task.updated", task({ id: "b", kind: "rank", status: "failed", error: "boom" }));
    });
    expect(success).toHaveBeenCalledWith("Self-test finished");
    expect(failure).toHaveBeenCalledWith("Ranking failed", { description: "boom" });
  });

  it("ignores malformed events", () => {
    renderStream();
    act(() => {
      FakeEventSource.latest().emit("task.updated", "{not json");
      FakeEventSource.latest().emit("task.updated", { nope: true });
    });
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("seeds from recent tasks and closes the stream on unmount", async () => {
    server.use(
      http.get("/api/tasks", () => HttpResponse.json([task({ id: "old", status: "running" })])),
    );
    const { unmount } = renderStream();
    await waitFor(() => {
      expect(screen.getByText("old:running:0.4")).toBeInTheDocument();
    });
    const source = FakeEventSource.latest();
    unmount();
    expect(source.closed).toBe(true);
  });
});
