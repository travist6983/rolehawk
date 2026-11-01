import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CircleSlashIcon,
  Loader2Icon,
  SearchIcon,
} from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useInvalidateSources,
  useLastScrape,
  useProfileOverview,
  useStartScrape,
  type PortalRun,
  type PortalView,
} from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useEventStream } from "@/features/events/EventStreamProvider";

import { plural, timeAgo } from "./sourceText";

const MAX_ERRORS_SHOWN = 3;

function RunRow({ run }: { run: PortalRun }) {
  const icon =
    run.status === "ok" ? (
      <CheckCircle2Icon className="size-4 text-score-high" aria-hidden />
    ) : run.status === "error" ? (
      <AlertTriangleIcon className="size-4 text-destructive" aria-hidden />
    ) : (
      <CircleSlashIcon className="size-4 text-muted-foreground" aria-hidden />
    );
  const extra = run.errors.length - MAX_ERRORS_SHOWN;
  return (
    <li className="py-2">
      <div className="flex items-center gap-2">
        {icon}
        <span className="font-medium">{run.name}</span>
        <span className="text-muted-foreground">
          {run.status === "skipped"
            ? `skipped: ${run.detail ?? ""}`
            : `${plural(run.new, "new job")} · ${run.matched.toLocaleString("en")} matching of ${run.found.toLocaleString("en")}`}
        </span>
      </div>
      {run.errors.length > 0 && (
        <ul className="mt-1 ml-6 space-y-0.5 text-xs text-muted-foreground">
          {run.errors.slice(0, MAX_ERRORS_SHOWN).map((error) => (
            <li key={error}>{error}</li>
          ))}
          {extra > 0 && <li>and {plural(extra, "more issue")}</li>}
        </ul>
      )}
    </li>
  );
}

export function SearchPanel({ portals }: { portals: PortalView[] }) {
  const overview = useProfileOverview();
  const targets = (overview.data?.search_targets ?? []).filter((t) => t.active);
  const last = useLastScrape();
  const start = useStartScrape();
  const invalidate = useInvalidateSources();
  const { tasks } = useEventStream();
  const running = tasks.find(
    (t) => t.kind === "scrape" && (t.status === "queued" || t.status === "running"),
  );

  // When the run we were watching ends, refresh the cards and the summary.
  const watching = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (watching.current && watching.current !== running?.id) invalidate();
    watching.current = running?.id;
  }, [running?.id, invalidate]);

  const ready = portals.filter((p) => p.enabled && p.ready);
  const countries = [...new Set(targets.map((t) => t.country))];
  const summary = last.data;
  const blocked =
    targets.length === 0
      ? "Add the job titles you're looking for first."
      : ready.length === 0
        ? "Switch on at least one ready source below."
        : null;

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <CardTitle>Search</CardTitle>
          <CardDescription>
            {targets.length > 0 ? (
              <>
                Looking for{" "}
                {targets.map((t, i) => (
                  <span key={t.id}>
                    {i > 0 && ", "}
                    <span className="font-medium text-foreground">{t.title}</span>
                  </span>
                ))}{" "}
                in {countries.join(", ")}, across {plural(ready.length, "ready source")}.
              </>
            ) : (
              "Searches use the target job titles from your profile."
            )}
          </CardDescription>
        </div>
        <Button
          disabled={blocked !== null || running !== undefined || start.isPending}
          onClick={() => {
            start.mutate(undefined, {
              onError: (error) => toast.error(errorText(error, "Couldn't start the search")),
            });
          }}
        >
          {running ? (
            <Loader2Icon className="animate-spin motion-reduce:animate-none" />
          ) : (
            <SearchIcon />
          )}
          {running ? "Searching…" : "Search now"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {blocked && (
          <p className="text-sm text-muted-foreground">
            {blocked}{" "}
            {targets.length === 0 && (
              <Link to="/profile" className="text-primary-text underline-offset-4 hover:underline">
                Set targets in Profile
              </Link>
            )}
          </p>
        )}
        <div aria-live="polite" className="empty:hidden">
          {running && (
            <div className="space-y-1.5">
              <Progress
                value={Math.round((running.progress ?? 0) * 100)}
                aria-label="Search progress"
              />
              <p className="text-sm text-muted-foreground">{running.message ?? "Starting…"}</p>
            </div>
          )}
        </div>
        {summary && (
          <div className="space-y-2">
            <p className="flex flex-wrap items-center gap-2 text-sm">
              <span>
                Last search {timeAgo(summary.finished_at)}:{" "}
                <span className="font-medium">{plural(summary.new, "new job")}</span>,{" "}
                {summary.duplicates.toLocaleString("en")} already seen
              </span>
              {summary.new > 0 && (
                <Badge variant="link" asChild>
                  <Link to="/discover">Review in Discover</Link>
                </Badge>
              )}
            </p>
            <details className="group rounded-lg border px-4 text-sm">
              <summary className="cursor-pointer py-2 text-muted-foreground select-none">
                Results by source
              </summary>
              <ul className="divide-y border-t">
                {/* Sources the user switched off aren't news; everything else is listed. */}
                {summary.portals
                  .filter((run) => !(run.status === "skipped" && run.detail === "off"))
                  .map((run) => (
                    <RunRow key={run.portal_id} run={run} />
                  ))}
              </ul>
            </details>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
