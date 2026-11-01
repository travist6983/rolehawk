import { CheckCircle2Icon, CircleAlertIcon, CircleDashedIcon } from "lucide-react";

import type { Bundle, RequirementView } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { KEYWORD_STATUS } from "./applicationText";

function Addressed({ value }: { value: boolean | null }) {
  if (value === null) return <span className="text-muted-foreground">Not reviewed</span>;
  return value ? (
    <span className="flex items-center gap-1 text-score-high">
      <CheckCircle2Icon aria-hidden className="size-3.5" /> Addressed
    </span>
  ) : (
    <span className="flex items-center gap-1 text-caution">
      <CircleAlertIcon aria-hidden className="size-3.5" /> Skipped
    </span>
  );
}

function RequirementRow({ item }: { item: RequirementView }) {
  const status = item.keyword ? KEYWORD_STATUS[item.keyword] : null;
  return (
    <tr className="border-t align-top">
      <td className="py-2 pr-3">
        <p className="font-medium">{item.requirement}</p>
        {item.note && <p className="text-xs text-muted-foreground">{item.note}</p>}
      </td>
      <td className="py-2 pr-3">
        <Badge variant={item.priority === "required" ? "secondary" : "outline"}>
          {item.priority === "required" ? "Required" : "Nice to have"}
        </Badge>
      </td>
      <td className="py-2 pr-3">
        {status ? (
          <span className={cn("block", status.tone)}>
            {status.label}
            {item.matched && item.keyword === "synonym" && (
              <span className="block text-xs text-muted-foreground">as {item.matched}</span>
            )}
          </span>
        ) : (
          <span className="text-muted-foreground">-</span>
        )}
      </td>
      <td className="py-2">
        <Addressed value={item.addressed} />
      </td>
    </tr>
  );
}

/** What the checks found: the posting's requirements and how the CV reads to an ATS. */
export function ChecksTab({ bundle }: { bundle: Bundle }) {
  const ats = bundle.ats;
  return (
    <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
      <section aria-labelledby="requirements-title" className="space-y-2">
        <h3 id="requirements-title" className="text-sm font-medium">
          The posting's requirements
        </h3>
        <p className="text-xs text-muted-foreground">
          Keyword matches are read from the CV file itself, the way an applicant tracking system
          reads it. Gaps stay gaps: they're never added to your CV.
        </p>
        {bundle.requirements.length === 0 ? (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            No requirements were listed for this draft. Rewrite a section or run Apply again to
            check them.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="pb-1 font-medium">
                    Requirement
                  </th>
                  <th scope="col" className="pb-1 font-medium">
                    Priority
                  </th>
                  <th scope="col" className="pb-1 font-medium">
                    In your CV
                  </th>
                  <th scope="col" className="pb-1 font-medium">
                    AI review
                  </th>
                </tr>
              </thead>
              <tbody>
                {bundle.requirements.map((item) => (
                  <RequirementRow key={item.requirement} item={item} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section aria-labelledby="ats-title" className="space-y-2 self-start rounded-lg border p-4">
        <h3 id="ats-title" className="text-sm font-medium">
          How an ATS reads your CV
        </h3>
        {ats ? (
          <>
            <p className="text-xs text-muted-foreground">
              Checked in the {ats.source === "pdf" ? "PDF" : "Word file"}'s text layer.
            </p>
            <ul className="space-y-2 text-sm">
              {ats.checks.map((check) => (
                <li key={check.name} className="flex gap-2">
                  {check.passed ? (
                    <CheckCircle2Icon
                      aria-hidden
                      className="mt-0.5 size-4 shrink-0 text-score-high"
                    />
                  ) : (
                    <CircleAlertIcon
                      aria-hidden
                      className="mt-0.5 size-4 shrink-0 text-destructive"
                    />
                  )}
                  <span>
                    <span className="font-medium">{check.name}</span>
                    <span className="sr-only">{check.passed ? " (passed)" : " (failed)"}</span>
                    <span className="block text-xs text-muted-foreground">{check.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <CircleDashedIcon aria-hidden className="size-4" /> Not checked yet. Save or rewrite to
            run it.
          </p>
        )}
      </section>
    </div>
  );
}
