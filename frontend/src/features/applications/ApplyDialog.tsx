import { AlertTriangleIcon, FileTextIcon, TerminalIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useApplyPlan, useInvalidateJobs, useStartApply, type ApplyPlan } from "@/api/queries";
import { ScoreBadge } from "@/components/ScoreBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { needsAttention } from "@/features/discover/discoverText";
import { FitGates } from "@/features/discover/FitDetails";
import { useEventStream } from "@/features/events/EventStreamProvider";
import { usd } from "@/lib/format";

import { readOutcome, type ApplyOutcome } from "./applicationText";

function FitSummary({ fit }: { fit: ApplyOutcome["fit"] | NonNullable<ApplyPlan["fit"]> }) {
  const gates = "gates" in fit ? fit.gates : null;
  return (
    <div className="space-y-2 rounded-lg border p-3 text-sm">
      <p className="flex items-center gap-2">
        <ScoreBadge score={fit.score} />
        <span>
          Fit score{" "}
          <span className="text-muted-foreground">(your threshold is {fit.threshold})</span>
        </span>
      </p>
      {fit.reasons.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
          {fit.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      {fit.must_have_gaps.length > 0 && (
        <p className="text-muted-foreground">Missing: {fit.must_have_gaps.join(", ")}</p>
      )}
      {gates && needsAttention(gates) && <FitGates gates={gates} />}
    </div>
  );
}

function Blockers({ plan }: { plan: ApplyPlan }) {
  if (!plan.has_profile) {
    return (
      <p className="flex gap-2 text-sm" role="alert">
        <AlertTriangleIcon className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
        <span>
          /apply tailors from your work experience, and your profile has none yet.{" "}
          <Link to="/profile" className="text-primary-text underline-offset-4 hover:underline">
            Add it in Profile
          </Link>
          .
        </span>
      </p>
    );
  }
  if (!plan.configured) {
    return (
      <div className="space-y-2 text-sm">
        <p>
          Writing uses Claude with your Anthropic API key, which isn't set up yet.{" "}
          <Link to="/settings" className="text-primary-text underline-offset-4 hover:underline">
            Add it in Settings
          </Link>
          .
        </p>
        <p className="flex gap-2 rounded-lg bg-muted/50 p-3 text-muted-foreground">
          <TerminalIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
          Using Claude Code? Run the /apply skill there; it drafts in your own session and saves
          here with the same fact checks.
        </p>
      </div>
    );
  }
  return null;
}

export function ApplyDialog({ jobId, onClose }: { jobId: number | null; onClose: () => void }) {
  const plan = useApplyPlan(jobId);
  const start = useStartApply();
  const navigate = useNavigate();
  const invalidateJobs = useInvalidateJobs();
  const stream = useEventStream();
  const [taskId, setTaskId] = useState<string | null>(null);
  const task = taskId ? stream.task(taskId) : undefined;
  const outcome = task?.status === "succeeded" ? readOutcome(task.result) : null;

  useEffect(() => {
    if (outcome?.application_id != null && outcome.status !== "below_threshold") {
      invalidateJobs();
      toast.success(
        outcome.status === "ready"
          ? "Your CV and cover letter are ready"
          : "Drafts ready: a few lines need your review",
      );
      onClose();
      void navigate(`/applications/${String(outcome.application_id)}`);
    }
  }, [outcome, navigate, onClose, invalidateJobs]);

  const go = (force: boolean) => {
    if (jobId === null) return;
    start.mutate(
      { job_id: jobId, force },
      {
        onSuccess: (ref) => {
          setTaskId(ref.task_id);
        },
        onError: (error) => toast.error(errorText(error, "Couldn't start /apply")),
      },
    );
  };

  const running = task && (task.status === "queued" || task.status === "running");
  const data = plan.data;
  const blocked = !data || !data.has_profile || !data.configured;

  return (
    <Dialog
      open={jobId !== null}
      onOpenChange={(open) => {
        if (!open && !running) {
          setTaskId(null);
          onClose();
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Apply to this job</DialogTitle>
          <DialogDescription>
            Claude writes a CV and cover letter tailored to this job using only what's in your
            profile, fact-checks every employer, title, date, degree, certification, and number,
            then creates Word and PDF files with your templates.
          </DialogDescription>
        </DialogHeader>

        {plan.isPending ? (
          <div className="space-y-2" aria-label="Checking the job">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : plan.isError ? (
          <p className="text-sm text-destructive">
            {errorText(plan.error, "Couldn't load the job")}
          </p>
        ) : running ? (
          <div className="space-y-2" aria-live="polite">
            <Progress
              value={Math.round((task.progress ?? 0) * 100)}
              aria-label="Application progress"
            />
            <p className="text-sm text-muted-foreground">{task.message ?? "Starting…"}</p>
          </div>
        ) : task?.status === "failed" ? (
          <p className="text-sm text-destructive" role="alert">
            {task.error ?? "Something went wrong."}
          </p>
        ) : outcome?.status === "below_threshold" ? (
          <div className="space-y-3">
            <p className="text-sm">
              This job scored below your threshold, so nothing was written. Apply anyway if you
              think the score misses something.
            </p>
            <FitSummary fit={outcome.fit} />
          </div>
        ) : data ? (
          <div className="space-y-3">
            {data.fit ? (
              <FitSummary fit={data.fit} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Not ranked yet: /apply scores it first and stops if it's below your threshold (
                {data.threshold}).
              </p>
            )}
            {data.application_id !== null && data.has_documents && (
              <p className="flex items-center gap-2 text-sm">
                <FileTextIcon className="size-4 text-muted-foreground" aria-hidden />
                You already have documents for this job.{" "}
                <Link
                  to={`/applications/${String(data.application_id)}`}
                  className="text-primary-text underline-offset-4 hover:underline"
                  onClick={onClose}
                >
                  Open them
                </Link>
              </p>
            )}
            <Blockers plan={data} />
            {!blocked && (
              <p className="text-sm text-muted-foreground">
                Estimated cost: about {usd(data.estimated_cost_usd)}.
              </p>
            )}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" disabled={Boolean(running)} onClick={onClose}>
            Cancel
          </Button>
          {outcome?.status === "below_threshold" ? (
            <Button
              disabled={start.isPending}
              onClick={() => {
                go(true);
              }}
            >
              Apply anyway
            </Button>
          ) : (
            <Button
              disabled={blocked || Boolean(running) || start.isPending}
              onClick={() => {
                go(false);
              }}
            >
              {data?.has_documents ? "Write new documents" : "Write CV and cover letter"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
