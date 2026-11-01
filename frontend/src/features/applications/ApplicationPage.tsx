import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ExternalLinkIcon,
  FileWarningIcon,
  SendIcon,
  WandSparklesIcon,
} from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";
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
import { PageHeader } from "@/components/layout/PageHeader";
import { ScoreBadge } from "@/components/ScoreBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { safeUrl, whereText } from "@/features/discover/discoverText";
import { timeAgo } from "@/lib/format";

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

function Header({ detail }: { detail: ApplicationDetail }) {
  const update = useUpdateApplication(detail.id);
  const autofill = useAutofill(detail.id);
  const [report, setReport] = useState<AutofillReport | null>(null);
  const link = safeUrl(detail.job.url);
  const hasDocs = detail.documents !== null;
  const flagged = detail.documents?.flags.length ?? 0;

  return (
    <>
      <PageHeader
        title={detail.job.title}
        description={`${detail.job.company} · ${whereText(detail.job)}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {link && (
              <Button variant="ghost" asChild>
                <a href={link} target="_blank" rel="noreferrer noopener">
                  <ExternalLinkIcon /> Posting
                </a>
              </Button>
            )}
            <Button
              variant="outline"
              disabled={!hasDocs || autofill.isPending}
              onClick={() => {
                autofill.mutate(undefined, {
                  onSuccess: setReport,
                  onError: (error) => toast.error(errorText(error, "Couldn't open the form")),
                });
              }}
            >
              <WandSparklesIcon /> {autofill.isPending ? "Opening…" : "Autofill application"}
            </Button>
            {detail.stage === "applying" || detail.stage === "saved" ? (
              <Button
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
                <SendIcon /> Mark as applied
              </Button>
            ) : null}
          </div>
        }
      />
      <div className="flex flex-wrap items-center gap-2 px-6 pt-4 text-sm">
        <Badge variant="secondary">{STAGE_LABELS[detail.stage]}</Badge>
        {detail.method === "autofill" && <Badge variant="outline">Autofilled</Badge>}
        {detail.applied_at && (
          <span className="text-muted-foreground">applied {timeAgo(detail.applied_at)}</span>
        )}
        {flagged > 0 && (
          <Badge variant="destructive" className="gap-1">
            <FileWarningIcon aria-hidden /> {flagged} line{flagged === 1 ? "" : "s"} to check
          </Badge>
        )}
      </div>
      {report && (
        <div className="px-6 pt-4">
          <AutofillResult report={report} />
        </div>
      )}
    </>
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
  return (
    <>
      <Header detail={detail} />
      <Tabs defaultValue={detail.documents ? "documents" : "job"} className="gap-4 p-6">
        <TabsList>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          {detail.documents && <TabsTrigger value="checks">Checks</TabsTrigger>}
          <TabsTrigger value="job">Job</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>
        <TabsContent value="documents">
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
              No documents yet. Use Apply on the job in Discover to write them.
            </p>
          )}
        </TabsContent>
        {detail.documents && (
          <TabsContent value="checks">
            <ChecksTab bundle={detail.documents} />
          </TabsContent>
        )}
        <TabsContent value="job">
          <JobTab detail={detail} />
        </TabsContent>
        <TabsContent value="timeline">
          <TimelineTab detail={detail} />
        </TabsContent>
      </Tabs>
    </>
  );
}
