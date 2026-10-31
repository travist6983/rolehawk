import { Loader2Icon } from "lucide-react";

import { Progress } from "@/components/ui/progress";

import { useRunningTasks } from "./EventStreamProvider";
import { taskLabel } from "./taskLabel";

/** Running background tasks with live progress. Announced politely to screen readers. */
export function ProgressTray() {
  const running = useRunningTasks();
  return (
    <section
      aria-label="Running tasks"
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 left-4 z-40 flex w-72 flex-col gap-2 md:left-60"
    >
      {running.map((task) => {
        const percent = task.progress == null ? null : Math.round(task.progress * 100);
        return (
          <div
            key={task.id}
            className="pointer-events-auto rounded-lg border bg-card p-3 text-card-foreground shadow-sm"
          >
            <div className="flex items-center gap-2 text-sm font-medium">
              <Loader2Icon className="size-4 animate-spin text-primary" aria-hidden />
              <span className="truncate">{taskLabel(task.kind)}</span>
              {percent !== null && (
                <span className="ml-auto font-mono text-xs text-muted-foreground">{percent}%</span>
              )}
            </div>
            {task.message && (
              <p className="mt-1 truncate text-xs text-muted-foreground">{task.message}</p>
            )}
            <Progress
              className="mt-2 h-1.5"
              value={percent ?? undefined}
              aria-label={`${taskLabel(task.kind)} progress`}
            />
          </div>
        );
      })}
    </section>
  );
}
