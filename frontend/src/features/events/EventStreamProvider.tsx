import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useReducer, useRef } from "react";
import { toast } from "sonner";

import { queryKeys, useRecentTasks, type TaskView } from "@/api/queries";

import { taskLabel } from "./taskLabel";

export type StreamStatus = "connecting" | "open" | "reconnecting";

/** The subset of EventSource the provider uses, so tests can inject a fake. */
export interface EventSourceLike {
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void;
  onopen: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
  close(): void;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

const defaultFactory: EventSourceFactory = (url) => new EventSource(url, { withCredentials: true }); // structural

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

interface State {
  status: StreamStatus;
  tasks: Record<string, TaskView>;
}

type Action =
  | { type: "status"; status: StreamStatus }
  | { type: "task"; task: TaskView }
  | { type: "seed"; tasks: TaskView[] };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "status":
      return state.status === action.status ? state : { ...state, status: action.status };
    case "task":
      return { ...state, tasks: { ...state.tasks, [action.task.id]: action.task } };
    case "seed": {
      const tasks = { ...state.tasks };
      for (const task of action.tasks) tasks[task.id] ??= task; // live updates win
      return { ...state, tasks };
    }
  }
}

function isTask(value: unknown): value is TaskView {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { id?: unknown }).id === "string" &&
    typeof (value as { status?: unknown }).status === "string"
  );
}

interface EventStreamValue {
  status: StreamStatus;
  tasks: TaskView[];
  task: (id: string) => TaskView | undefined;
}

const EventStreamContext = createContext<EventStreamValue | null>(null);

export function EventStreamProvider({
  children,
  url = "/api/events",
  factory = defaultFactory,
}: {
  children: React.ReactNode;
  url?: string;
  factory?: EventSourceFactory;
}) {
  const [state, dispatch] = useReducer(reducer, { status: "connecting", tasks: {} });
  const queryClient = useQueryClient();
  const recent = useRecentTasks();
  const seen = useRef(new Map<string, string>());

  useEffect(() => {
    if (recent.data) {
      for (const task of recent.data) seen.current.set(task.id, task.status);
      dispatch({ type: "seed", tasks: recent.data });
    }
  }, [recent.data]);

  useEffect(() => {
    const source = factory(url);
    let opened = false;
    source.onopen = () => {
      dispatch({ type: "status", status: "open" });
      if (opened) void queryClient.invalidateQueries({ queryKey: queryKeys.tasks }); // resync
      opened = true;
    };
    source.onerror = () => {
      dispatch({ type: "status", status: "reconnecting" }); // EventSource retries by itself
    };
    source.addEventListener("task.updated", (event) => {
      let task: unknown;
      try {
        task = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!isTask(task)) return;
      const previous = seen.current.get(task.id);
      seen.current.set(task.id, task.status);
      dispatch({ type: "task", task });
      if (previous !== undefined && !TERMINAL.has(previous) && TERMINAL.has(task.status)) {
        const label = taskLabel(task.kind);
        if (task.status === "succeeded") toast.success(`${label} finished`);
        else if (task.status === "failed")
          toast.error(`${label} failed`, { description: task.error ?? undefined });
        else toast(`${label} cancelled`);
      }
    });
    return () => {
      source.close();
    };
  }, [factory, url, queryClient]);

  const value = useMemo<EventStreamValue>(() => {
    const tasks = Object.values(state.tasks).sort((a, b) =>
      b.created_at.localeCompare(a.created_at),
    );
    return { status: state.status, tasks, task: (id) => state.tasks[id] };
  }, [state]);

  return <EventStreamContext.Provider value={value}>{children}</EventStreamContext.Provider>;
}

/** Live connection status and task progress from /api/events. */
export function useEventStream(): EventStreamValue {
  const value = useContext(EventStreamContext);
  if (!value) throw new Error("useEventStream must be used inside <EventStreamProvider>");
  return value;
}

export function useRunningTasks(): TaskView[] {
  return useEventStream().tasks.filter((t) => t.status === "queued" || t.status === "running");
}
