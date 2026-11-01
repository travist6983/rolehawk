import { ArchiveIcon, SquareKanbanIcon } from "lucide-react";
import { Link } from "react-router";
import { useState } from "react";

import { errorText } from "@/api/errors";
import { useLLMStatus, usePipeline, useStaleApplications } from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { BoardSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";

import { Kanban } from "./Kanban";
import { greeting, waitingText, waitsOnYou } from "./pipelineText";
import { StaleDialog } from "./StaleDialog";
import { PRODUCT_NAME } from "@/lib/brand";
import { isMac } from "@/lib/hotkeys";

export default function PipelinePage() {
  const status = useLLMStatus();
  const board = usePipeline();
  const stale = useStaleApplications();
  const [sweeping, setSweeping] = useState(false);
  const connected = status.data?.configured === true;
  const quiet = stale.data ?? [];
  const cards = board.data?.columns.flatMap((c) => c.cards) ?? [];
  const waiting = cards.filter(waitsOnYou).length;
  const header = (
    <PageHeader
      title="Pipeline"
      description={
        board.data && board.data.total > 0 ? (
          <>
            {greeting()}. <b className="font-semibold text-foreground">{waitingText(waiting)}</b>
          </>
        ) : (
          "Every application, from saved to offer."
        )
      }
      actions={
        <>
          {board.data && board.data.total > 0 && (
            <span className="hidden text-[13.5px] font-medium text-muted-foreground lg:inline">
              Drag a card, or focus it and press {isMac() ? "⌥" : "Alt"} ← →
            </span>
          )}
          {quiet.length > 0 && (
            <Button
              variant="outline"
              onClick={() => {
                setSweeping(true);
              }}
            >
              <ArchiveIcon /> No reply in 60+ days ({quiet.length})
            </Button>
          )}
          <Button variant="outline" asChild>
            <Link to="/discover">Add a job</Link>
          </Button>
        </>
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
          description={errorText(board.error, `The ${PRODUCT_NAME} backend didn't answer.`)}
        />
      </>
    );
  }
  if (board.data.total > 0) {
    return (
      <>
        {header}
        <div className="px-5 pb-7 md:px-8">
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
