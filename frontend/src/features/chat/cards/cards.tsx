import {
  ArrowRightIcon,
  CheckCircle2Icon,
  FileTextIcon,
  Loader2Icon,
  PlayIcon,
  XCircleIcon,
} from "lucide-react";
import { Link } from "react-router";

import { ApiError } from "@/api/client";
import { useRunCommand } from "@/api/queries";
import { ScoreBadge } from "@/components/ScoreBadge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useEventStream } from "@/features/events/EventStreamProvider";
import { taskLabel } from "@/features/events/taskLabel";
import { ProposalChip } from "@/features/memory/ProposalChip";

import type { ChatCard } from "../types";
import { registerCard } from "./registry";

type Card<T extends string> = Extract<ChatCard, { type: T }>;

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border bg-card p-3 text-sm">{children}</div>;
}

export function TaskCard({ card }: { card: { task_id: string; command: string } }) {
  const task = useEventStream().task(card.task_id);
  const status = task?.status ?? "queued";
  const percent = task?.progress == null ? undefined : Math.round(task.progress * 100);
  const Icon =
    status === "succeeded" ? CheckCircle2Icon : status === "failed" ? XCircleIcon : Loader2Icon;
  return (
    <Shell>
      <div className="flex items-center gap-2 font-medium">
        <Icon
          aria-hidden
          className={
            status === "succeeded"
              ? "size-4 text-score-high"
              : status === "failed"
                ? "size-4 text-destructive"
                : "size-4 animate-spin text-primary"
          }
        />
        {taskLabel(card.command)}
        <span className="ml-auto text-xs text-muted-foreground capitalize">{status}</span>
      </div>
      {task?.message && <p className="mt-1 text-xs text-muted-foreground">{task.message}</p>}
      {(status === "queued" || status === "running") && (
        <Progress
          className="mt-2 h-1.5"
          value={percent}
          aria-label={`${taskLabel(card.command)} progress`}
        />
      )}
      {task?.error && <p className="mt-1 text-xs text-destructive">{task.error}</p>}
    </Shell>
  );
}

function CommandResultCard({ card }: { card: Card<"command_result"> }) {
  return (
    <Shell>
      <p className="font-medium">/{card.command}</p>
      <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted/50 p-2 font-mono text-xs whitespace-pre-wrap">
        {JSON.stringify(card.result, null, 2)}
      </pre>
    </Shell>
  );
}

function CommandProposalCard({ card }: { card: Card<"command_proposal"> }) {
  const run = useRunCommand();
  const started = run.data?.task_id;
  return (
    <Shell>
      <p className="font-medium">Run /{card.command}?</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{card.description}</p>
      {Object.keys(card.params).length > 0 && (
        <pre className="mt-2 rounded bg-muted/50 p-2 font-mono text-xs">
          {JSON.stringify(card.params)}
        </pre>
      )}
      {run.isIdle || run.isPending ? (
        <Button
          size="sm"
          className="mt-2"
          disabled={run.isPending}
          onClick={() => {
            run.mutate({ name: card.command, params: card.params });
          }}
        >
          <PlayIcon /> Run
        </Button>
      ) : run.isError ? (
        <p className="mt-2 text-xs text-destructive">
          {run.error instanceof ApiError ? run.error.message : "The command failed."}
        </p>
      ) : started ? (
        <div className="mt-2">
          <TaskCard card={{ task_id: started, command: card.command }} />
        </div>
      ) : (
        <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted/50 p-2 font-mono text-xs">
          {JSON.stringify(run.data.result, null, 2)}
        </pre>
      )}
    </Shell>
  );
}

function JobCard({ card }: { card: Card<"job"> }) {
  return (
    <Shell>
      <div className="flex items-start gap-3">
        {card.score != null && <ScoreBadge score={card.score} />}
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{card.title}</p>
          <p className="truncate text-xs text-muted-foreground">
            {card.company}
            {card.location ? ` · ${card.location}` : ""}
          </p>
        </div>
        <Button
          asChild
          size="sm"
          variant="ghost"
          aria-label={`Open ${card.title} at ${card.company}`}
        >
          <Link to={`/discover?job=${String(card.job_id)}`}>
            <ArrowRightIcon />
          </Link>
        </Button>
      </div>
    </Shell>
  );
}

function DocumentCard({ card }: { card: Card<"document"> }) {
  return (
    <Shell>
      <p className="font-medium">{card.label}</p>
      <ul className="mt-2 space-y-1">
        {card.files.map((file) => (
          <li key={file.path} className="flex items-center gap-2 text-xs">
            <FileTextIcon className="size-3.5 text-muted-foreground" aria-hidden />
            <span className="font-mono">{file.name}</span>
          </li>
        ))}
      </ul>
      <Button asChild size="sm" variant="outline" className="mt-2">
        <Link to={`/applications/${String(card.application_id)}`}>Review documents</Link>
      </Button>
    </Shell>
  );
}

function StageProposalCard({ card }: { card: Card<"stage_proposal"> }) {
  return (
    <Shell>
      <p className="font-medium">{card.company}</p>
      <p className="mt-1 text-xs">
        Move from <span className="font-medium capitalize">{card.from_stage ?? "new"}</span> to{" "}
        <span className="font-medium capitalize">{card.to_stage}</span>?
      </p>
      {card.evidence && (
        <blockquote className="mt-2 border-l-2 pl-2 text-xs text-muted-foreground">
          {card.evidence}
        </blockquote>
      )}
      <Button asChild size="sm" variant="outline" className="mt-2">
        <Link to={`/applications/${String(card.application_id)}`}>Review in timeline</Link>
      </Button>
    </Shell>
  );
}

function MemoryProposalCard({ card }: { card: Card<"memory_proposal"> }) {
  return <ProposalChip proposal={card.proposal} />;
}

registerCard("memory_proposal", MemoryProposalCard);
registerCard("command_proposal", CommandProposalCard);
registerCard("command_result", CommandResultCard);
registerCard("task", TaskCard);
registerCard("job", JobCard);
registerCard("document", DocumentCard);
registerCard("stage_proposal", StageProposalCard);
