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
