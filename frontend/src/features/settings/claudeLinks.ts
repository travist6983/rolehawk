/** The Claude Platform (formerly the Anthropic Console), where API keys and billing live. */
export const CLAUDE_PLATFORM_URL = "https://platform.claude.com/";
export const CLAUDE_BILLING_URL = "https://platform.claude.com/settings/billing";
export const CLAUDE_KEYS_URL = "https://platform.claude.com/settings/keys";

/** Monthly spend limits offered during setup; null means no limit. */
export const CAP_CHOICES = [10, 25, 50, null] as const;
export const DEFAULT_CAP = 25;

export function capLabel(cap: number | null): string {
  return cap === null ? "No limit" : `$${String(cap)} a month`;
}
