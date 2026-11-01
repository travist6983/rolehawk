import { GitCompareArrowsIcon } from "lucide-react";

import type { Draft } from "@/api/queries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Conflict = Draft["conflicts"][number];

/** One choice per fact your documents (or your profile) state differently. */
export function ConflictPicker({
  conflicts,
  picks,
  onPick,
}: {
  conflicts: Conflict[];
  picks: Record<string, number>;
  onPick: (id: string, option: number) => void;
}) {
  if (conflicts.length === 0) return null;
  return (
    <Card className="border-caution/60">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <GitCompareArrowsIcon aria-hidden className="size-4 text-caution" />
          {conflicts.length === 1
            ? "1 thing your documents disagree on"
            : `${String(conflicts.length)} things your documents disagree on`}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Employers compare your CV with LinkedIn. Pick the version that's right for each one.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {conflicts.map((conflict) => (
          <fieldset key={conflict.id} className="space-y-2">
            <legend className="text-sm">
              <span className="font-medium">{conflict.subject}</span>
              <span className="text-muted-foreground">: {conflict.question}</span>
            </legend>
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={conflict.subject}>
              {conflict.options.map((option, index) => {
                const checked = picks[conflict.id] === index;
                return (
                  <button
                    key={`${option.label}-${option.source}`}
                    type="button"
                    role="radio"
                    aria-checked={checked}
                    onClick={() => {
                      onPick(conflict.id, index);
                    }}
                    className={cn(
                      "rounded-md border px-3 py-1.5 text-left text-sm transition-colors focus-visible:outline-2",
                      checked ? "border-primary bg-primary/5" : "hover:bg-muted",
                    )}
                  >
                    <span className="block font-medium">{option.label}</span>
                    {option.source && (
                      <span className="block text-xs text-muted-foreground">
                        from {option.source}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </fieldset>
        ))}
      </CardContent>
    </Card>
  );
}
