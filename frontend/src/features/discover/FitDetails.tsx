import { CheckCircle2Icon, CircleAlertIcon, OctagonXIcon } from "lucide-react";

import type { JobDetail } from "@/api/queries";
import { cn } from "@/lib/utils";

import { FIT_PARTS, gateText, type GateVerdict } from "./discoverText";

type Breakdown = NonNullable<JobDetail["breakdown"]>;
type Gates = NonNullable<JobDetail["gates"]>;

/** The four parts behind the score, as labeled meters (one hue; text in text tokens). */
export function FitBreakdown({ breakdown }: { breakdown: Breakdown }) {
  return (
    <div>
      <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        How it adds up
      </h3>
      <dl className="mt-2 space-y-2">
        {FIT_PARTS.map((part) => {
          const value = breakdown[part.key];
          return (
            <div key={part.key} className="grid grid-cols-[7rem_1fr_2rem] items-center gap-2">
              <dt className="text-xs" title={part.hint}>
                {part.label} <span className="text-muted-foreground">{part.weight}%</span>
              </dt>
              <div
                className="h-1.5 overflow-hidden rounded-full bg-muted"
                role="meter"
                aria-label={part.label}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={value}
              >
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${String(value)}%` }}
                />
              </div>
              <dd className="text-right text-xs tabular-nums">{value}</dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}

const ICONS: Record<GateVerdict, typeof CheckCircle2Icon> = {
  pass: CheckCircle2Icon,
  check: CircleAlertIcon,
  fail: OctagonXIcon,
};
const TONES: Record<GateVerdict, string> = {
  pass: "text-score-high",
  check: "text-caution",
  fail: "text-destructive",
};

/** Eligibility and language gates with the posting's own words, and any deal breaker. */
export function FitGates({ gates }: { gates: Gates }) {
  const rows = [
    { key: "eligibility" as const, gate: gates.eligibility },
    { key: "language" as const, gate: gates.language },
  ];
  return (
    <ul className="space-y-1.5" aria-label="Fit checks">
      {rows.map(({ key, gate }) => {
        const Icon = ICONS[gate.verdict];
        return (
          <li key={key} className="flex gap-2 text-sm">
            <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", TONES[gate.verdict])} />
            <span>
              <span className={cn(gate.verdict !== "pass" && "font-medium")}>
                {gateText(key, gate.verdict)}
              </span>
              {gate.quote && (
                <span className="block text-xs text-muted-foreground">
                  The posting says: &ldquo;{gate.quote}&rdquo;
                </span>
              )}
            </span>
          </li>
        );
      })}
      {gates.deal_breaker && (
        <li className="flex gap-2 text-sm">
          <OctagonXIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-destructive" />
          <span className="font-medium">Hits your deal-breaker: {gates.deal_breaker}</span>
        </li>
      )}
    </ul>
  );
}

/** Why a job might not fit, compactly (the apply dialog and application page). */
export function FitConcerns({ concerns }: { concerns: string[] }) {
  if (concerns.length === 0) return null;
  return (
    <div>
      <p className="text-muted-foreground">Might not fit:</p>
      <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
        {concerns.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
    </div>
  );
}
