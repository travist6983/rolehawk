import {
  BookmarkIcon,
  BookmarkXIcon,
  FileTextIcon,
  SendIcon,
  EyeOffIcon,
  ExternalLinkIcon,
  SparklesIcon,
  Undo2Icon,
} from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useDismissJobs, useJob, useSaveJobs, type JobDetail } from "@/api/queries";
import { ScoreBadge } from "@/components/ScoreBadge";
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

import { safeUrl, whereText } from "./discoverText";
import { IntegrityNotice } from "./IntegrityNotice";

function FitSection({ job, onRank }: { job: JobDetail; onRank: () => void }) {
  if (job.score === null) {
    return (
      <section aria-label="Fit" className="rounded-lg border border-dashed p-4 text-sm">
        <p className="font-medium">Not ranked yet</p>
        <p className="mt-1 text-muted-foreground">
          Rank it to see how well it fits your profile, with reasons and gaps.
        </p>
        <Button size="sm" variant="outline" className="mt-3" onClick={onRank}>
          <SparklesIcon /> Rank this job
        </Button>
      </section>
    );
  }
  return (
    <section aria-label="Fit" className="space-y-3 rounded-lg border p-4 text-sm">
      <div className="flex items-center gap-2">
        <ScoreBadge score={job.score} className="text-sm" />
        <span className="font-medium">Fit score</span>
        {job.scored_at && (
          <span className="text-xs text-muted-foreground">ranked {timeAgo(job.scored_at)}</span>
        )}
      </div>
      {job.reasons.length > 0 && (
        <div>
          <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Why</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {job.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Gaps in must-haves
        </h3>
        {job.must_have_gaps.length > 0 ? (
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {job.must_have_gaps.map((gap) => (
              <li key={gap}>
                <Badge variant="outline">{gap}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-muted-foreground">None found.</p>
        )}
      </div>
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
        <Button size="sm" asChild>
          <Link to={`/applications/${String(job.application_id)}`}>
            <FileTextIcon /> Open application
          </Link>
        </Button>
      ) : (
        <Button
          size="sm"
          disabled={busy}
          onClick={() => {
            onApply(job.id);
          }}
        >
          <SendIcon /> Apply
        </Button>
      )}
      {job.stage === null ? (
        <Button
          size="sm"
          disabled={busy}
          onClick={() => {
            save.mutate(
              { ids: [job.id] },
              { onSuccess: () => toast.success("Saved to your pipeline"), onError },
            );
          }}
        >
          <BookmarkIcon /> Save
        </Button>
      ) : job.stage === "saved" ? (
        <Button
          size="sm"
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
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => {
              dismiss.mutate(
                { ids: [job.id] },
                { onSuccess: () => toast("Dismissed. It won't be ranked again."), onError },
              );
            }}
          >
            <EyeOffIcon /> Dismiss
          </Button>
        )
      )}
      {link && (
        <Button size="sm" variant="ghost" asChild>
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
      <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-xl">
        {data ? (
          <>
            <SheetHeader className="pr-10">
              <SheetTitle className="text-lg leading-snug">{data.title}</SheetTitle>
              <SheetDescription>
                {data.company} · {whereText(data)}
              </SheetDescription>
              <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                {data.salary_text && <span>{data.salary_text}</span>}
                <span>via {data.source}</span>
                <span>posted {timeAgo(data.posted_at ?? data.scraped_at)}</span>
              </p>
            </SheetHeader>
            <div className="space-y-5 px-4 pb-6">
              <Actions job={data} onApply={onApply} />
              <FitSection
                job={data}
                onRank={() => {
                  onRank(data.id);
                }}
              />
              <section aria-labelledby="posting-heading" className="space-y-2">
                <h3 id="posting-heading" className="text-sm font-medium">
                  From the posting
                </h3>
                <p className="text-xs text-muted-foreground">
                  Written by the employer. Hidden text and invisible characters are removed.
                </p>
                <IntegrityNotice report={data.integrity_report} />
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
