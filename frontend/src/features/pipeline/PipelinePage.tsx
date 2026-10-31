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
            title: connected ? "Build your profile" : "Connect Claude",
            description: connected
              ? "Upload a resume or answer a short interview."
              : "Add your Anthropic API key. It stays in your keychain.",
            action: connected
              ? { label: "Open profile", to: "/profile" }
              : { label: "Connect", to: "/settings" },
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
