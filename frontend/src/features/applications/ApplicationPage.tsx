import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ExternalLinkIcon,
  FileWarningIcon,
  WandSparklesIcon,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useApplication,
  useAutofill,
  useFollowUpHistory,
  useUpdateApplication,
  type ApplicationDetail,
  type AutofillReport,
} from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { DocumentSkeleton } from "@/components/feedback/Skeletons";
import { ScoreBadge } from "@/components/ScoreBadge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { safeUrl, whereText } from "@/features/discover/discoverText";
import { FitConcerns } from "@/features/discover/FitDetails";
import { plural, timeAgo } from "@/lib/format";
import { fitWord } from "@/lib/score";
import { cn } from "@/lib/utils";

import { CHANNEL_LABELS, STAGE_LABELS } from "./applicationText";
import { ChecksTab } from "./ChecksTab";
import { DocumentsTab, type Doc } from "./DocumentsTab";

function AutofillResult({ report }: { report: AutofillReport }) {
  return (
    <div className="space-y-1.5 rounded-lg border p-3 text-sm" aria-live="polite">
      <p className="flex items-center gap-2 font-medium">
        <CheckCircle2Icon className="size-4 text-score-high" aria-hidden />
        The application form is open in a separate browser window. Nothing has been submitted.
      </p>
      {report.note && <p className="text-muted-foreground">{report.note}</p>}
      {report.filled.length > 0 && (
        <p className="text-muted-foreground">Filled: {report.filled.join(", ")}</p>
      )}
      {report.attached.length > 0 && (
        <p className="text-muted-foreground">Attached: {report.attached.join(", ")}</p>
      )}
      {report.needs_you.length > 0 && (
        <p className="flex gap-1.5 text-destructive">
          <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
          Still needs you: {report.needs_you.join("; ")}
        </p>
      )}
      <p className="text-muted-foreground">
        Check everything, submit it in that window, then mark this application as applied.
      </p>
    </div>
  );
}

const TAB_LABELS: Record<string, string> = {
  documents: "Documents",
  checks: "Checks",
  job: "Job",
  timeline: "Timeline",
};

type StepState = "done" | "now" | "todo";

/** One of the design's progress steps: a ringed circle (check when done) and two lines. */
function Step({ label, note, state }: { label: string; note: string; state: StepState }) {
  return (
    <li className="flex items-center gap-2">
      <span
        aria-hidden
        className={cn(
          "grid size-[22px] place-items-center rounded-full text-xs font-semibold",
          state === "done" && "bg-foreground text-background",
          state === "now" && "text-primary-text shadow-[0_0_0_1.5px_var(--primary)]",
          state === "todo" && "shadow-[0_0_0_1.5px_var(--border)]",
        )}
      >
        {state === "done" ? "✓" : state === "now" ? "•" : ""}
      </span>
      <span className="flex flex-col">
        <span className="text-sm font-semibold">
          {label}
          <span className="sr-only">
            {state === "done" ? ", done" : state === "now" ? ", in progress" : ", to do"}
          </span>
        </span>
        <span className="text-[13px] text-muted-foreground">{note}</span>
      </span>
    </li>
  );
}

function stepsFor(detail: ApplicationDetail): { label: string; note: string; state: StepState }[] {
  const docs = detail.documents;
  const flagsOn = (document: "cv" | "cover_letter") =>
    docs?.flags.filter((f) => f.document === document).length ?? 0;
  const sent = !["saved", "applying"].includes(detail.stage);
  const cvFlags = flagsOn("cv");
  const letterFlags = flagsOn("cover_letter");
  const closes = detail.job.closes_at;
  const ready = docs !== null && cvFlags + letterFlags === 0;
  return [
    {
      label: "Resume",
      note: !docs ? "Not written yet" : cvFlags ? plural(cvFlags, "flag") : "Tailored",
      state: !docs ? "todo" : cvFlags ? "now" : "done",
    },
    {
      label: "Cover letter",
      note: !docs ? "Not written yet" : letterFlags ? plural(letterFlags, "flag") : "Ready",
      state: !docs ? "todo" : letterFlags ? "now" : "done",
    },
    {
      label: "Submit",
      note: sent
        ? detail.applied_at
          ? `Applied ${timeAgo(detail.applied_at)}`
          : "Sent"
        : closes
          ? `Closes ${new Date(`${closes}T00:00:00`).toLocaleDateString("en", { month: "short", day: "numeric" })}`
          : "On the employer's site",
      state: sent ? "done" : ready ? "now" : "todo",
    },
  ];
}

function Header({ detail }: { detail: ApplicationDetail }) {
  return (
    <div className="flex flex-col gap-[22px] px-5 pt-[26px] md:px-8">
      <nav aria-label="Breadcrumb" className="flex gap-2 text-sm font-medium text-muted-foreground">
        <Link to="/" className="text-foreground-2 underline underline-offset-[3px]">
          Pipeline
        </Link>
        <span aria-hidden>/</span>
        <span>{detail.job.company}</span>
      </nav>
      <header className="flex flex-wrap items-end gap-6">
        <div className="flex flex-col gap-1.5">
          <span className="text-[12.5px] font-semibold tracking-[0.04em] text-foreground-2 uppercase">
            {detail.job.company}
          </span>
          <h1 className="font-serif text-4xl leading-[1.05] font-medium tracking-[-0.02em] md:text-[40px]">
            {detail.job.title}
          </h1>
          <p className="text-sm text-foreground-2">
            {whereText(detail.job)} · {STAGE_LABELS[detail.stage]}
            {detail.method === "autofill" && " · Autofilled"}
          </p>
        </div>
        <ol aria-label="Progress" className="ml-auto flex flex-wrap gap-[22px]">
          {stepsFor(detail).map((step) => (
            <Step key={step.label} {...step} />
          ))}
        </ol>
      </header>
    </div>
  );
}

/** The right-hand column: lines to check, the fit, and the next step. */
function Aside({
  detail,
  onReviewFlags,
}: {
  detail: ApplicationDetail;
  onReviewFlags: () => void;
}) {
  const update = useUpdateApplication(detail.id);
  const autofill = useAutofill(detail.id);
  const [report, setReport] = useState<AutofillReport | null>(null);
  const link = safeUrl(detail.job.url);
  const docs = detail.documents;
  const flags = docs?.flags ?? [];
  const fit = docs?.fit;
  const first = flags[0];
  const open = detail.stage === "applying" || detail.stage === "saved";

  return (
    <aside className="flex w-full flex-col gap-4 lg:sticky lg:top-4 lg:max-w-[380px] lg:flex-[1_1_300px]">
      {first && (
        <section
          aria-label="Lines to check"
          className="flex flex-col gap-2.5 rounded-lg bg-flag px-[18px] pt-[18px] pb-4 text-flag-foreground"
        >
          <span className="text-[12.5px] font-semibold tracking-[0.04em] uppercase">
            {flags.length === 1 ? "1 line to check" : `${String(flags.length)} lines to check`}
          </span>
          <span className="font-serif text-[19px] leading-tight font-medium">
            Check before you send
          </span>
          <span className="text-[14.5px] leading-normal">{first.issue}</span>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button onClick={onReviewFlags}>Review flagged lines</Button>
          </div>
        </section>
      )}
      {fit && (
        <section
          aria-label="Fit"
          className="flex flex-col gap-2.5 rounded-lg bg-card p-[18px] shadow-card"
        >
          <div className="flex items-baseline gap-2">
            <ScoreBadge score={fit.score} className="text-[30px]" />
            <span className="text-sm font-medium text-foreground-2">{fitWord(fit.score)}</span>
          </div>
          {fit.reasons[0] && (
            <span className="text-[14.5px] leading-normal text-foreground-2">
              Strongest match: {fit.reasons[0]}
            </span>
          )}
        </section>
      )}
      {open && (
        <div className="flex flex-col gap-2">
          <Button
            size="lg"
            disabled={update.isPending}
            onClick={() => {
              update.mutate(
                { stage: "applied" },
                {
                  onSuccess: () => toast.success("Marked as applied"),
                  onError: (error) => toast.error(errorText(error, "Couldn't update")),
                },
              );
            }}
          >
            Mark as applied
          </Button>
          <span className="text-center text-[13.5px] text-muted-foreground">
            {flags.length > 0
              ? "Resolve the flagged lines, then submit on the employer's site"
              : "Submit on the employer's site first. Nothing is sent from here."}
          </span>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={docs === null || autofill.isPending}
          onClick={() => {
            autofill.mutate(undefined, {
              onSuccess: setReport,
              onError: (error) => toast.error(errorText(error, "Couldn't open the form")),
            });
          }}
        >
          <WandSparklesIcon /> {autofill.isPending ? "Opening…" : "Autofill application"}
        </Button>
        {link && (
          <Button variant="ghost" className="text-foreground-2" asChild>
            <a href={link} target="_blank" rel="noreferrer noopener">
              <ExternalLinkIcon /> Posting
            </a>
          </Button>
        )}
      </div>
      {report && <AutofillResult report={report} />}
    </aside>
  );
}

function JobTab({ detail }: { detail: ApplicationDetail }) {
  const job = detail.job;
  const fit = detail.documents?.fit;
  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <section aria-labelledby="posting-title" className="space-y-2">
        <h3 id="posting-title" className="text-sm font-medium">
          From the posting
        </h3>
        <p className="text-xs text-muted-foreground">Written by the employer and shown as-is.</p>
        <div className="text-sm leading-relaxed break-words whitespace-pre-line">
          {job.description || "No description was included."}
        </div>
      </section>
      {fit && (
        <section aria-label="Fit" className="space-y-2 self-start rounded-lg border p-4 text-sm">
          <p className="flex items-center gap-2 font-medium">
            <ScoreBadge score={fit.score} /> Fit score
          </p>
          <ul className="list-disc space-y-1 pl-5">
            {fit.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <FitConcerns concerns={fit.concerns} />
          {fit.must_have_gaps.length > 0 && (
            <p className="text-muted-foreground">Missing: {fit.must_have_gaps.join(", ")}</p>
          )}
        </section>
      )}
    </div>
  );
}

function TimelineTab({ detail }: { detail: ApplicationDetail }) {
  const followUps = useFollowUpHistory(detail.id);
  const entries = [
    ...detail.history.map((event) => ({
      at: event.created_at,
      key: `stage-${event.created_at}-${event.to_stage}`,
      title: STAGE_LABELS[event.to_stage],
      detail: event.from_stage ? `from ${STAGE_LABELS[event.from_stage]}` : null,
      body: null,
    })),
    ...(followUps.data ?? []).map((note) => ({
      at: note.sent_at,
      key: `followup-${String(note.id)}`,
      title: `Follow-up sent (${CHANNEL_LABELS[note.channel]})`,
      detail: note.subject,
      body: note.body,
    })),
  ].sort((a, b) => b.at.localeCompare(a.at));
  return (
    <ol className="space-y-3 border-l pl-4" aria-label="Stage history">
      {entries.map((entry) => (
        <li key={entry.key} className="text-sm">
          <span className="font-medium">{entry.title}</span>
          {entry.detail && <span className="text-muted-foreground"> {entry.detail}</span>}
          <span className="block text-xs text-muted-foreground">{timeAgo(entry.at)}</span>
          {entry.body && (
            <p className="mt-1 max-w-prose text-xs whitespace-pre-line text-muted-foreground">
              {entry.body}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}

export default function ApplicationPage() {
  const params = useParams();
  const id = Number(params.id);
  const application = useApplication(Number.isInteger(id) ? id : -1);
  const [doc, setDoc] = useState<Doc>("cv");
  const [chosenTab, setTab] = useState<string | null>(null);

  if (application.isPending) return <DocumentSkeleton />;
  if (application.isError) {
    return (
      <EmptyState
        icon={FileWarningIcon}
        title="Application not found"
        description={errorText(application.error, "It may have been removed.")}
      />
    );
  }
  const detail = application.data;
  const tab = chosenTab ?? (detail.documents ? "documents" : "job");
  return (
    <>
      <Header detail={detail} />
      <div className="flex flex-wrap items-start gap-7 px-5 pt-[22px] pb-8 md:px-8">
        <Tabs
          value={tab}
          onValueChange={setTab}
          className="min-w-0 flex-[1_1_520px] gap-0 rounded-lg bg-card shadow-card"
        >
          <TabsList className="h-auto w-full justify-start gap-1 border-b px-4 md:px-6">
            {["documents", "checks", "job", "timeline"]
              .filter((value) => value !== "checks" || detail.documents)
              .map((value) => (
                <TabsTrigger
                  key={value}
                  value={value}
                  className="flex-none px-2.5 pt-3.5 pb-3 text-[14.5px] data-[state=active]:text-foreground"
                >
                  {TAB_LABELS[value]}
                </TabsTrigger>
              ))}
          </TabsList>
          <TabsContent value="documents" className="p-4 md:p-6">
            {detail.documents ? (
              <DocumentsTab
                key={detail.documents.updated_at}
                applicationId={detail.id}
                bundle={detail.documents}
                doc={doc}
                onDocChange={setDoc}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                No documents yet. Use Write application on the job in Discover to write them.
              </p>
            )}
          </TabsContent>
          {detail.documents && (
            <TabsContent value="checks" className="p-4 md:p-6">
              <ChecksTab bundle={detail.documents} />
            </TabsContent>
          )}
          <TabsContent value="job" className="p-4 md:p-6">
            <JobTab detail={detail} />
          </TabsContent>
          <TabsContent value="timeline" className="p-4 md:p-6">
            <TimelineTab detail={detail} />
          </TabsContent>
        </Tabs>
        <Aside
          detail={detail}
          onReviewFlags={() => {
            setTab("checks");
          }}
        />
      </div>
    </>
  );
}
