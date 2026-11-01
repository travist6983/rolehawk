import { fitWord, rulerPercent } from "@/lib/score";
import { cn } from "@/lib/utils";

function label(score: number): string {
  return `Fit score ${String(score)} out of 100`;
}

/** The fit score as a number in the display face. Compact: for chat cards and inline text. */
export function ScoreBadge({ score, className }: { score: number; className?: string }) {
  return (
    <span
      className={cn("font-serif text-xl leading-none font-medium tabular-nums", className)}
      aria-label={label(score)}
    >
      {score}
    </span>
  );
}

/** The design's fit ruler: the score, then a hairline from 50 to 100 with a tick at 75 and a
 *  marker where this score falls. */
export function FitRuler({ score, className }: { score: number; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)} role="img" aria-label={label(score)}>
      <span className="w-7 font-serif text-xl leading-none font-medium tabular-nums">{score}</span>
      <span aria-hidden className="relative h-2 flex-1 border-b border-muted-foreground">
        <span className="absolute bottom-0 left-1/2 h-1 w-px bg-muted-foreground" />
        <span
          className="absolute -bottom-[3px] h-[11px] w-[3px] rounded-[1px] bg-foreground"
          style={{ left: `${String(rulerPercent(score))}%` }}
        />
      </span>
    </div>
  );
}

/** The large version for a job's detail: score, its word, and a labeled 50 / 75 / 100 scale. */
export function FitScale({ score }: { score: number }) {
  return (
    <div className="space-y-2" role="img" aria-label={`${label(score)}, ${fitWord(score)}`}>
      <div className="flex items-baseline gap-2" aria-hidden>
        <span className="font-serif text-[34px] leading-none font-medium tabular-nums">
          {score}
        </span>
        <span className="text-sm font-medium text-foreground-2">{fitWord(score)}</span>
      </div>
      <div aria-hidden className="relative h-3.5 border-b border-foreground-2">
        <span className="absolute bottom-0 left-0 h-1.5 w-px bg-foreground-2" />
        <span className="absolute bottom-0 left-1/2 h-1.5 w-px bg-foreground-2" />
        <span className="absolute right-0 bottom-0 h-1.5 w-px bg-foreground-2" />
        <span
          className="absolute -bottom-1 h-4 w-[3px] rounded-[1px] bg-foreground"
          style={{ left: `${String(rulerPercent(score))}%` }}
        />
      </div>
      <div aria-hidden className="flex justify-between font-mono text-xs text-muted-foreground">
        <span>50</span>
        <span>75</span>
        <span>100</span>
      </div>
    </div>
  );
}
