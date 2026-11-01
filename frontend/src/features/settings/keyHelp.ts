import type { KeyTest } from "@/api/queries";

import { CLAUDE_BILLING_URL, CLAUDE_KEYS_URL } from "./claudeLinks";

/** Where a key problem gets fixed on the Claude Platform. */
export function fixLink(link: KeyTest["fix_link"]): { href: string; label: string } | null {
  if (link === "keys") return { href: CLAUDE_KEYS_URL, label: "Open API keys" };
  if (link === "billing") return { href: CLAUDE_BILLING_URL, label: "Open Billing" };
  return null;
}

/** A monthly estimate in whole dollars, the way people say prices out loud. */
export function roughDollars(usd: number): string {
  return usd < 1 ? "under $1" : `about $${String(Math.round(usd))}`;
}
