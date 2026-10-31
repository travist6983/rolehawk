import { AlertTriangleIcon, SparklesIcon, TerminalIcon } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useModels, useRankPlan, useStartRank, type RankPlan } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { plural, usd } from "@/lib/format";

import { skippedSummary } from "./discoverText";

function PlanDetails({ plan }: { plan: RankPlan }) {
  const models = useModels(plan.configured);
  const modelName = models.data?.find((m) => m.id === plan.model)?.display_name ?? plan.model;
  const skipped = skippedSummary(plan.filtered);

  if (!plan.configured) {
    return (
      <div className="space-y-3 text-sm">
        <p>
          Ranking uses Claude with your own Anthropic API key, which isn't set up yet.{" "}
          <Link to="/settings" className="text-primary-text underline-offset-4 hover:underline">
            Add it in Settings
          </Link>
          .
        </p>
        <div className="flex gap-3 rounded-lg bg-muted/50 p-3">
          <TerminalIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <p className="text-muted-foreground">
            Using Claude Code? Run the <span className="font-mono">/rank</span> skill there to score
            these jobs in your own session; no key needed here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 text-sm">
      {plan.candidates === 0 ? (
        <p>Nothing new to rank.</p>
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
          <dt className="text-muted-foreground">Jobs</dt>
          <dd className="font-medium">
            {plural(plan.candidates, "job")} in {plural(plan.batches, "batch", "batches")}
          </dd>
          <dt className="text-muted-foreground">Model</dt>
          <dd>{modelName}</dd>
          <dt className="text-muted-foreground">Estimated cost</dt>
          <dd className="font-medium">about {usd(plan.estimated_cost_usd)}</dd>
          <dt className="text-muted-foreground">This month</dt>
          <dd>
            {usd(plan.month_to_date_usd)} spent
            {plan.cap_usd !== null && ` of your ${usd(plan.cap_usd)} cap`}
          </dd>
        </dl>
      )}
      {plan.remaining > 0 && (
        <p className="text-muted-foreground">
          {plural(plan.remaining, "more job")} will be left for the next run.
        </p>
      )}
      {skipped && <p className="text-muted-foreground">{skipped}</p>}
      {plan.exceeds_cap && (
        <p className="flex gap-2 text-destructive" role="alert">
          <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
          This would go over your monthly spend cap. Raise it in Settings to continue.
        </p>
      )}
    </div>
  );
}

export function RankDialog({
  open,
  jobIds,
  onOpenChange,
  onStarted,
}: {
  open: boolean;
  jobIds?: number[];
  onOpenChange: (open: boolean) => void;
  onStarted?: () => void;
}) {
  const [rescore, setRescore] = useState(false);
  const params = { job_ids: jobIds ?? null, rescore };
  const plan = useRankPlan(params, open);
  const start = useStartRank();
  const rescoreId = useId();
  const ready =
    plan.data !== undefined &&
    plan.data.configured &&
    plan.data.candidates > 0 &&
    !plan.data.exceeds_cap;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {jobIds ? `Rank ${plural(jobIds.length, "selected job")}` : "Rank new jobs"}
          </DialogTitle>
          <DialogDescription>
            Claude scores each job 0 to 100 against your profile, with reasons and the must-haves
            you're missing. Jobs outside your locations, below your salary floor, or matching a deal
            breaker are skipped first, at no cost.
          </DialogDescription>
        </DialogHeader>
        {plan.isPending ? (
          <div className="space-y-2" aria-label="Estimating cost">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-3/5" />
          </div>
        ) : plan.isError ? (
          <p className="text-sm text-destructive">{errorText(plan.error, "Couldn't estimate")}</p>
        ) : (
          <PlanDetails plan={plan.data} />
        )}
        <div className="flex items-center gap-2">
          <Checkbox
            id={rescoreId}
            checked={rescore}
            onCheckedChange={(checked) => {
              setRescore(checked === true);
            }}
          />
          <Label htmlFor={rescoreId} className="text-sm font-normal">
            Also re-rank jobs that already have a score
          </Label>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          <Button
            disabled={!ready || start.isPending}
            onClick={() => {
              start.mutate(params, {
                onSuccess: () => {
                  onOpenChange(false);
                  onStarted?.();
                },
                onError: (error) => toast.error(errorText(error, "Couldn't start ranking")),
              });
            }}
          >
            <SparklesIcon />
            {plan.data && plan.data.candidates > 0
              ? `Rank ${plural(plan.data.candidates, "job")}`
              : "Rank"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
