import { CheckIcon, XIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useResolveProposal, type ProposalView } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const FILE_LABELS: Record<string, string> = {
  profile: "Profile",
  preferences: "Preferences",
  facts: "Facts",
};

function summary(p: ProposalView): string {
  if (p.op === "remove") return `Remove "${p.old_text ?? ""}"`;
  if (p.op === "replace") return `Change "${p.old_text ?? ""}" to "${p.text ?? ""}"`;
  return p.text ?? "";
}

/** A proposed memory edit with accept/reject. Memory only changes when the user accepts. */
export function ProposalChip({
  proposal,
  className,
}: {
  proposal: ProposalView;
  className?: string;
}) {
  const resolve = useResolveProposal();
  const [status, setStatus] = useState(proposal.status);
  const pending = status === "pending";

  const act = (action: "accept" | "reject") => {
    resolve.mutate(
      { id: proposal.id, action },
      {
        onSuccess: (updated) => {
          setStatus(updated.status);
          if (action === "accept")
            toast.success(`Saved to ${FILE_LABELS[proposal.target] ?? "memory"}`);
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === 409) setStatus("conflict");
          toast.error(error instanceof ApiError ? error.message : "Couldn't update memory");
        },
      },
    );
  };

  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-lg border bg-card p-3 text-sm",
        !pending && "opacity-70",
        className,
      )}
    >
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {FILE_LABELS[proposal.target] ?? proposal.target}
          {proposal.section ? ` · ${proposal.section}` : ""}
        </p>
        <p className="mt-0.5 break-words">{summary(proposal)}</p>
        {proposal.reason && <p className="mt-1 text-xs text-muted-foreground">{proposal.reason}</p>}
      </div>
      {pending ? (
        <div className="flex shrink-0 gap-1">
          <Button
            size="icon"
            variant="outline"
            className="size-8"
            aria-label="Accept memory update"
            disabled={resolve.isPending}
            onClick={() => {
              act("accept");
            }}
          >
            <CheckIcon />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="size-8"
            aria-label="Reject memory update"
            disabled={resolve.isPending}
            onClick={() => {
              act("reject");
            }}
          >
            <XIcon />
          </Button>
        </div>
      ) : (
        <span className="shrink-0 text-xs text-muted-foreground capitalize">{status}</span>
      )}
    </div>
  );
}
