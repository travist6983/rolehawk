import { AlertTriangleIcon, CheckCircle2Icon, ExternalLinkIcon } from "lucide-react";

import type { KeyTest } from "@/api/queries";
import { cn } from "@/lib/utils";

import { fixLink } from "./keyHelp";

/** The outcome of a key test in plain words, with the one link that fixes it. */
export function KeyTestResult({ result, className }: { result: KeyTest; className?: string }) {
  const link = fixLink(result.fix_link);
  return (
    <div
      role="status"
      aria-label="Key test"
      className={cn(
        "flex gap-3 rounded-lg border p-3 text-sm",
        result.ok ? "border-score-high/40" : "border-caution/50",
        className,
      )}
    >
      {result.ok ? (
        <CheckCircle2Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-score-high" />
      ) : (
        <AlertTriangleIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-caution" />
      )}
      <div className="min-w-0 space-y-1">
        <p className="font-medium">{result.title}</p>
        <p className="text-muted-foreground">{result.fix}</p>
        {link && (
          <a
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-primary-text underline-offset-4 hover:underline"
          >
            {link.label} <ExternalLinkIcon className="size-3.5" aria-hidden />
          </a>
        )}
      </div>
    </div>
  );
}
