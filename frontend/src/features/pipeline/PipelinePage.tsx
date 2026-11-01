import { ArchiveIcon, SquareKanbanIcon } from "lucide-react";
import { useState } from "react";

import { errorText } from "@/api/errors";
import { useLLMStatus, usePipeline, useStaleApplications } from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { BoardSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";

import { Kanban } from "./Kanban";
import { StaleDialog } from "./StaleDialog";

export default function PipelinePage() {
  const status = useLLMStatus();
  const board = usePipeline();
  const stale = useStaleApplications();
  const [sweeping, setSweeping] = useState(false);
  const connected = status.data?.configured === true;
  const quiet = stale.data ?? [];
  const header = (
    <PageHeader
      title="Pipeline"
      description="Every application, from saved to offer."
      actions={
        quiet.length > 0 ? (
          <Button
            variant="outline"
            onClick={() => {
              setSweeping(true);
            }}
          >
            <ArchiveIcon /> No reply in 60+ days ({quiet.length})
          </Button>
        ) : undefined
      }
    />
  );
  if (board.isPending) return <BoardSkeleton />;
  if (board.isError) {
    return (
      <>
        {header}
        <EmptyState
          icon={SquareKanbanIcon}
          title="Couldn't load your pipeline"
          description={errorText(board.error, "The Offerbound backend didn't answer.")}
        />
      </>
    );
  }
  if (board.data.total > 0) {
    return (
      <>
        {header}
        <div className="p-6">
          <Kanban board={board.data} />
        </div>
        {sweeping && (
          <StaleDialog
            applications={quiet}
            onClose={() => {
              setSweeping(false);
            }}
          />
        )}
      </>
    );
  }
  return (
    <>
      {header}
      <EmptyState
        icon={SquareKanbanIcon}
        title="No applications yet"
        description="Three steps get you to your first tailored application."
        steps={[
          {
            title: "Build your profile",
            description: connected
              ? "Import a resume or answer a short interview."
              : "Connect Claude, then import a resume or answer a short interview.",
            action: { label: "Get started", to: "/onboarding" },
          },
          {
            title: "Find jobs",
            description: "Pick job sources and run a search for your target roles.",
            action: { label: "Choose sources", to: "/sources" },
          },
          {
            title: "Review your shortlist",
            description: "See ranked jobs with fit reasons, then draft an application.",
            action: { label: "Discover jobs", to: "/discover" },
          },
        ]}
      />
    </>
  );
}
