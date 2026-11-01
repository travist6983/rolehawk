import { AlertCircleIcon, CheckIcon, Loader2Icon } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { ProposalChip } from "@/features/memory/ProposalChip";
import { cn } from "@/lib/utils";

import { CardRenderer } from "./cards/CardRenderer";
import type { ChatItem, ToolActivity } from "./types";

const TOOL_LABELS: Record<string, string> = {
  query_pipeline: "Checked your pipeline",
  run_command: "Ran a command",
  propose_memory_update: "Suggested a memory update",
};

const SUGGESTIONS = ["What should I do first?", "Who have I applied to this month?", "/spend"];

function ToolChip({ tool }: { tool: ToolActivity }) {
  const Icon =
    tool.status === "running" ? Loader2Icon : tool.status === "error" ? AlertCircleIcon : CheckIcon;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
      <Icon aria-hidden className={cn("size-3", tool.status === "running" && "animate-spin")} />
      {TOOL_LABELS[tool.name] ?? tool.name}
    </span>
  );
}

function EmptyChat({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <div>
        <p className="font-serif text-xl font-medium italic">Ask about your search</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Claude can see your profile and pipeline. Type <kbd className="font-mono">/</kbd> for
          commands.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((text) => (
          <Button
            key={text}
            size="sm"
            variant="outline"
            className="font-medium text-foreground-2"
            onClick={() => {
              onPick(text);
            }}
          >
            {text}
          </Button>
        ))}
      </div>
    </div>
  );
}

export function MessageList({
  items,
  onPick,
}: {
  items: ChatItem[];
  onPick: (text: string) => void;
}) {
  const end = useRef<HTMLDivElement>(null);
  const last = items[items.length - 1];
  const lastLength = last?.kind === "assistant" ? last.text.length + last.cards.length : 0;

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [items.length, lastLength]);

  if (items.length === 0) return <EmptyChat onPick={onPick} />;

  const streaming = last?.kind === "assistant" && last.status === "streaming";
  return (
    <div className="flex-1 space-y-3.5 overflow-y-auto p-5" role="log" aria-label="Conversation">
      {items.map((item) =>
        item.kind === "user" ? (
          <div key={item.id} className="flex justify-end">
            <p className="max-w-[88%] rounded-xl bg-sidebar px-3.5 py-2.5 text-[15px] leading-normal whitespace-pre-wrap text-sidebar-foreground">
              {item.text}
            </p>
          </div>
        ) : (
          <div key={item.id} className="space-y-2">
            {item.tools.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {item.tools.map((tool) => (
                  <ToolChip key={tool.id} tool={tool} />
                ))}
              </div>
            )}
            {(item.text || item.status === "streaming") && (
              <p className="max-w-[88%] rounded-xl bg-card px-3.5 py-3 text-[15px] leading-normal whitespace-pre-wrap shadow-[0_0_0_1px_var(--border)]">
                {item.text}
                {item.status === "streaming" && (
                  <span
                    className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-foreground/60 align-text-bottom"
                    aria-hidden
                  />
                )}
              </p>
            )}
            {item.cards.map((card, index) => (
              <CardRenderer key={`${item.id}-card-${String(index)}`} card={card} />
            ))}
            {item.proposals.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Remember this?</p>
                {item.proposals.map((proposal) => (
                  <ProposalChip key={proposal.id} proposal={proposal} />
                ))}
              </div>
            )}
            {item.status === "error" && (
              <p role="alert" className="flex items-center gap-1.5 text-sm text-destructive">
                <AlertCircleIcon className="size-4" aria-hidden />
                {item.error ?? "Something went wrong."}
              </p>
            )}
            {item.status === "stopped" && <p className="text-xs text-muted-foreground">Stopped.</p>}
          </div>
        ),
      )}
      <p className="sr-only" aria-live="polite">
        {streaming ? "Claude is replying" : "Reply complete"}
      </p>
      <div ref={end} />
    </div>
  );
}
