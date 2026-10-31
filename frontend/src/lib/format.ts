/** Small display formatters shared across screens. */

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** "just now", "5 minutes ago", "yesterday". */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  if (seconds < 45) return "just now";
  const format = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of UNITS) {
    if (seconds >= size) return format.format(-Math.round(seconds / size), unit);
  }
  return format.format(-1, "minute");
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count.toLocaleString("en")} ${count === 1 ? one : many}`;
}

/** "$0.42", or "under $0.01" for tiny estimates. */
export function usd(amount: number): string {
  if (amount > 0 && amount < 0.01) return "under $0.01";
  return `$${amount.toFixed(2)}`;
}
