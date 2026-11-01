import { CircleDollarSignIcon } from "lucide-react";

import type { TypicalCost } from "@/api/queries";

import { roughDollars } from "./keyHelp";

/** What a month usually costs with the current model choices, priced by the backend. */
export function TypicalCostNote({ cost }: { cost: TypicalCost }) {
  const { active, light } = cost;
  return (
    <div className="flex gap-3 rounded-lg bg-muted/50 p-3 text-sm">
      <CircleDollarSignIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="space-y-1.5">
        <p>
          <span className="font-medium">
            Typical cost: {roughDollars(active.monthly_usd)} a month
          </span>{" "}
          for an active search (ranking {active.jobs_ranked_per_week} jobs, writing{" "}
          {active.applications_per_week} applications and sending {active.chat_messages_per_week}{" "}
          chat messages a week), {roughDollars(light.monthly_usd)} for light use.
        </p>
        <p className="text-muted-foreground">
          Writing and chat use {cost.writing_model} and ranking uses {cost.ranking_model}, at
          Anthropic's current prices. Every big task shows its cost before it runs. A Claude Pro or
          Max subscription can't be used by other apps, so this is billed separately on the Claude
          Platform.
        </p>
      </div>
    </div>
  );
}
