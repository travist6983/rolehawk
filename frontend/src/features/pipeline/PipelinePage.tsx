import { SquareKanbanIcon } from "lucide-react";

import { errorText } from "@/api/errors";
import { useLLMStatus, usePipeline } from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { BoardSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";

import { Kanban } from "./Kanban";

export default function PipelinePage() {
  const status = useLLMStatus();
  const board = usePipeline();
  const connected = status.data?.configured === true;
  const header = (
    <PageHeader title="Pipeline" description="Every application, from saved to offer." />
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
