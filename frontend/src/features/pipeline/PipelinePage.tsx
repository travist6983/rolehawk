import { SquareKanbanIcon } from "lucide-react";

import { useLLMStatus } from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";

export default function PipelinePage() {
  const status = useLLMStatus();
  const connected = status.data?.configured === true;
  return (
    <>
      <PageHeader title="Pipeline" description="Every application, from saved to offer." />
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
