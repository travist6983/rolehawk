import { ChartColumnIcon, SearchXIcon } from "lucide-react";
import { Link } from "react-router";

import { useLLMStatus } from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";

/** Screens whose features ship in later releases. Each teaches what will appear and how. */

export function InsightsPage() {
  const status = useLLMStatus();
  return (
    <>
      <PageHeader title="Insights" description="Your funnel, response rates, and spend." />
      <EmptyState
        icon={ChartColumnIcon}
        title="Not enough data yet"
        description="Charts fill in as you apply. Your AI spend is tracked from the first call."
      >
        {status.data && (
          <p className="text-sm">
            Spend this month:{" "}
            <span className="font-mono font-semibold">
              ${status.data.month_to_date_usd.toFixed(2)}
            </span>
          </p>
        )}
      </EmptyState>
    </>
  );
}

export function NotFoundPage() {
  return (
    <EmptyState icon={SearchXIcon} title="Page not found" description="That page doesn't exist.">
      <Button asChild>
        <Link to="/">Back to pipeline</Link>
      </Button>
    </EmptyState>
  );
}
