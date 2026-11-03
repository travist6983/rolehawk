import {
  BookmarkXIcon,
  FileTextIcon,
  ExternalLinkIcon,
  SparklesIcon,
  Undo2Icon,
} from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useDismissJobs, useJob, useSaveJobs, type JobDetail } from "@/api/queries";
import { FitScale } from "@/components/ScoreBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

import { OUTSIDE_DETAIL, deadlineText, safeUrl, staleText, whereText } from "./discoverText";
import { FitBreakdown, FitGates } from "./FitDetails";
import { IntegrityNotice } from "./IntegrityNotice";

function FitList({ items, marker, tone }: { items: string[]; marker: string; tone: string }) {
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item} className="grid grid-cols-[14px_1fr] gap-1.5 text-[14.5px] leading-normal">
          <span aria-hidden className={tone}>
            {marker}
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function Concerns({ concerns, onRescore }: { concerns: string[] | null; onRescore: () => void }) {
  return (
    <div className="space-y-2">
      <h3 className="font-serif text-lg font-medium italic">Why it might not fit</h3>
      {concerns === null ? (
        <p className="text-muted-foreground">
          This score is from before RoleHawk listed concerns.{" "}
          <button
            type="button"
            className="text-primary-text underline-offset-4 hover:underline"
            onClick={onRescore}
          >
            Rank it again
          </button>{" "}
          to see them.
        </p>
      ) : concerns.length > 0 ? (
        <FitList items={concerns} marker="−" tone="text-caution" />
      ) : (
        <p className="text-muted-foreground">Nothing stands out against it.</p>
      )}
    </div>
  );
}

function FitSection({ job, onRank }: { job: JobDetail; onRank: () => void }) {
  if (job.score === null) {
    return (
      <section aria-label="Fit" className="rounded-lg border border-dashed p-4 text-sm">
        <p className="font-medium">Not ranked yet</p>
        <p className="mt-1 text-muted-foreground">
          Rank it to see how well it fits your profile, with reasons and gaps.
        </p>
        {job.outside_preferences && (
          <p className="mt-2 text-muted-foreground">
            <span className="font-medium text-foreground">Outside your preferences.</span>{" "}
            {OUTSIDE_DETAIL[job.outside_preferences]} Ranking new jobs skips it, but you can rank it
            here.
          </p>
        )}
        <Button size="sm" variant="outline" className="mt-3" onClick={onRank}>
          <SparklesIcon /> Rank this job
        </Button>
      </section>
    );
  }
  return (
    <section aria-label="Fit" className="space-y-4 text-sm">
      <div className="space-y-1">
        <p className="flex items-baseline justify-between text-xs font-semibold tracking-[0.04em] text-muted-foreground uppercase">
          <span>Fit score</span>
          {job.scored_at && (
            <span className="font-normal tracking-normal normal-case">
              ranked {timeAgo(job.scored_at)}
            </span>
          )}
        </p>
        <FitScale score={job.score} />
      </div>
      {job.gates && <FitGates gates={job.gates} />}
      {job.reasons.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-serif text-lg font-medium italic">Why this fits you</h3>
          <FitList items={job.reasons} marker="+" tone="text-score-high" />
        </div>
      )}
      <Concerns concerns={job.concerns} onRescore={onRank} />
      <div className="space-y-2">
        <h3 className="font-serif text-lg font-medium italic">Worth addressing</h3>
        {job.must_have_gaps.length > 0 ? (
          <FitList items={job.must_have_gaps} marker="–" tone="text-primary-text" />
        ) : (
          <p className="text-muted-foreground">No gaps in the must-haves.</p>
        )}
      </div>
      {job.breakdown && <FitBreakdown breakdown={job.breakdown} />}
    </section>
  );
}

function Actions({ job, onApply }: { job: JobDetail; onApply: (id: number) => void }) {
  const save = useSaveJobs();
  const dismiss = useDismissJobs();
  const busy = save.isPending || dismiss.isPending;
  const onError = (error: unknown) => toast.error(errorText(error, "Couldn't update the job"));
  const inPipeline = job.stage !== null && job.stage !== "saved";
  const link = safeUrl(job.url);

  return (
    <div className="flex flex-wrap gap-2">
      {job.application_id !== null && job.stage !== null && job.stage !== "saved" ? (
        <Button asChild>
          <Link to={`/applications/${String(job.application_id)}`}>
            <FileTextIcon /> Open application
          </Link>
        </Button>
      ) : (
        <Button
          disabled={busy}
          onClick={() => {
            onApply(job.id);
          }}
        >
          Write application
        </Button>
      )}
      {job.stage === null ? (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => {
            save.mutate(
              { ids: [job.id] },
              { onSuccess: () => toast.success("Saved to your pipeline"), onError },
            );
          }}
        >
          Save
        </Button>
      ) : job.stage === "saved" ? (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => {
            save.mutate({ ids: [job.id], saved: false }, { onError });
          }}
        >
          <BookmarkXIcon /> Unsave
        </Button>
      ) : (
        <Badge variant="secondary">In your pipeline: {job.stage}</Badge>
      )}
      {job.dismissed ? (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => {
            dismiss.mutate({ ids: [job.id], dismissed: false }, { onError });
          }}
        >
          <Undo2Icon /> Restore
        </Button>
      ) : (
        !inPipeline && (
          <Button
            variant="ghost"
            className="text-foreground-2"
            disabled={busy}
            onClick={() => {
              dismiss.mutate(
                { ids: [job.id] },
                { onSuccess: () => toast("Dismissed. It won't be ranked again."), onError },
              );
            }}
          >
            Dismiss
          </Button>
        )
      )}
      {link && (
        <Button variant="ghost" className="text-foreground-2" asChild>
          <a href={link} target="_blank" rel="noreferrer noopener">
            <ExternalLinkIcon /> Open posting
          </a>
        </Button>
      )}
    </div>
  );
}

export function JobDetailSheet({
  id,
  onClose,
  onRank,
  onApply,
}: {
  id: number | null;
  onClose: () => void;
  onRank: (id: number) => void;
  onApply: (id: number) => void;
}) {
  const job = useJob(id);
  const data = job.data;

  return (
    <Sheet
      open={id !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent className="w-full gap-0 overflow-y-auto bg-card sm:w-1/3 sm:max-w-none sm:min-w-[460px]">
        {data ? (
          <>
            <SheetHeader className="gap-1 px-6 pt-6 pr-12">
              <p className="text-[12.5px] font-semibold tracking-[0.04em] text-foreground-2 uppercase">
                {data.company}
              </p>
              <SheetTitle className="font-serif text-[28px] leading-[1.15] font-medium tracking-[-0.01em]">
                {data.title}
              </SheetTitle>
              <SheetDescription className="text-sm text-foreground-2">
                {[
                  whereText(data),
                  data.salary_text,
                  data.posted_at || data.portal_id !== "manual"
                    ? `posted ${timeAgo(data.posted_at ?? data.scraped_at)}`
                    : `added ${timeAgo(data.scraped_at)}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </SheetDescription>
              <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>via {data.source}</span>
                {deadlineText(data) && (
                  <span className={cn(data.deadline && "font-medium text-caution")}>
                    {deadlineText(data)}
                  </span>
                )}
              </p>
              {data.stale_days !== null && (
                <p className="text-xs text-caution">
                  {staleText(data)}. Some postings stay open for months; check it's still live
                  before applying.
                </p>
              )}
            </SheetHeader>
            <div className="space-y-6 px-6 pb-8">
              <FitSection
                job={data}
                onRank={() => {
                  onRank(data.id);
                }}
              />
              <Actions job={data} onApply={onApply} />
              <section aria-labelledby="posting-heading" className="space-y-2">
                <h3 id="posting-heading" className="font-serif text-lg font-medium italic">
                  From the posting
                </h3>
                <p className="text-xs text-muted-foreground">
                  Written by the employer. Hidden text and invisible characters are removed.
                </p>
                <IntegrityNotice report={data.integrity_report} />
                {data.summary_only && (
                  <p className="rounded-lg bg-muted/50 p-3 text-sm text-muted-foreground">
                    {data.source} shares only a short summary of this posting. Open the posting for
                    the full text.
                  </p>
                )}
                <div className="text-sm leading-relaxed break-words whitespace-pre-line">
                  {data.description || "No description was included."}
                </div>
              </section>
            </div>
          </>
        ) : (
          <div className="space-y-3 p-4" aria-label="Loading job">
            <SheetTitle className="sr-only">Loading job</SheetTitle>
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-32 w-full" />
            {job.isError && (
              <p className="text-sm text-destructive">
                {errorText(job.error, "Couldn't load the job")}
              </p>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
