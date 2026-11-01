import { LightbulbIcon, SparklesIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useCalibrate, useCalibrationStatus, type CalibrationResult } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ProposalChip } from "@/features/memory/ProposalChip";

/** Learn from results: patterns in what got interviews, offered as preference edits. */
export function CalibrationCard() {
  const status = useCalibrationStatus();
  const calibrate = useCalibrate();
  const [result, setResult] = useState<CalibrationResult | null>(null);
  const data = status.data;
  if (!data) return null;

  return (
    <section
      aria-labelledby="calibration-title"
      className="space-y-3 rounded-xl border bg-card p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="calibration-title" className="flex items-center gap-2 font-medium">
            <LightbulbIcon aria-hidden className="size-4 text-primary-text" /> Learn from your
            results
          </h2>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">
            {data.ready
              ? `${String(data.positive)} of your ${String(data.resolved)} finished applications got an interview. Claude can compare them and suggest changes to your preferences, so future scores lean toward what works.`
              : `After ${String(data.needed)} applications get a result (an interview, a rejection, or no reply), Claude can look for patterns in what works. ${String(data.resolved)} so far.`}
          </p>
        </div>
        <Button
          variant="outline"
          disabled={!data.ready || calibrate.isPending}
          onClick={() => {
            calibrate.mutate(undefined, {
              onSuccess: setResult,
              onError: (error) => toast.error(errorText(error, "Couldn't look for patterns")),
            });
          }}
        >
          <SparklesIcon /> {calibrate.isPending ? "Looking…" : "Find patterns"}
        </Button>
      </div>
      {result && (
        <div className="space-y-3">
          {result.findings.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No clear patterns yet. Try again after a few more results.
            </p>
          ) : (
            <ul className="space-y-2 text-sm" aria-label="Patterns">
              {result.findings.map((finding) => (
                <li key={finding.pattern} className="flex flex-wrap items-baseline gap-2">
                  <span>{finding.pattern}</span>
                  <Badge variant={finding.strength === "firm" ? "secondary" : "outline"}>
                    {finding.strength === "firm" ? "Firm" : "Worth watching"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
          {result.proposals.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">
                Suggested changes to your preferences (nothing changes until you accept)
              </p>
              {result.proposals.map((proposal) => (
                <ProposalChip key={proposal.id} proposal={proposal} />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
