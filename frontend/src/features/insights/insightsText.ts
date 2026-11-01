/** Pure helpers for Insights. */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${String(Math.round(value * 100))}%`;
}

/** "2026-10-26" -> "Oct 26" (dates are UTC week starts; no time-zone shifting). */
export function weekLabel(iso: string): string {
  const [, month, day] = iso.split("-");
  const name = MONTHS[Number(month) - 1] ?? month ?? "";
  return `${name} ${String(Number(day))}`;
}

export function compactNumber(value: number): string {
  return value >= 10_000
    ? new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value)
    : value.toLocaleString("en");
}

interface SourceLike {
  source: string;
  applied: number;
  responses: number;
  rate: number;
}

/** The headline sentence over Insights, in the design's voice: what's working, from the
 *  numbers only. Null when there's nothing to say yet. */
export function leadText(
  sources: SourceLike[],
  totals: { applied: number; responses: number },
): { before: string; strong: string; after: string } | null {
  const sent = sources.filter((s) => s.applied > 0);
  const best = [...sent].sort((a, b) => b.rate - a.rate)[0];
  const worst = [...sent].sort((a, b) => a.rate - b.rate)[0];
  if (best && worst && best !== worst && worst.rate > 0 && best.rate >= worst.rate * 1.5) {
    const ratio = best.rate / worst.rate;
    const times = ratio >= 1.95 ? `${String(Math.round(ratio))} times as often` : "more often";
    return {
      before: `Applications from ${best.source} get a reply `,
      strong: times,
      after: ` as those from ${worst.source}.`,
    };
  }
  if (totals.applied === 0) return null;
  return {
    before: "",
    strong: `${String(totals.responses)} of ${String(totals.applied)}`,
    after: ` applications you sent got a reply.`,
  };
}
