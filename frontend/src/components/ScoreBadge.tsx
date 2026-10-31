import { scoreTone } from "@/lib/score";
import { cn } from "@/lib/utils";

const TONE_CLASSES = {
  high: "border-score-high/30 bg-score-high/10 text-score-high",
  mid: "border-score-mid/30 bg-score-mid/10 text-score-mid",
  low: "border-score-low/30 bg-score-low/10 text-score-low",
} as const;

export function ScoreBadge({ score, className }: { score: number; className?: string }) {
  const tone = scoreTone(score);
  return (
    <span
      className={cn(
        "inline-flex min-w-9 items-center justify-center rounded-md border px-1.5 py-0.5 font-mono text-xs font-semibold tabular-nums",
        TONE_CLASSES[tone],
        className,
      )}
      aria-label={`Fit score ${String(score)} out of 100`}
    >
      {score}
    </span>
  );
}
