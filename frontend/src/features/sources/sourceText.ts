/** Pure helpers for the Sources screen: pasted watchlist parsing and display text. */

import type { PortalDefinition } from "@/api/queries";

export { plural, timeAgo } from "@/lib/format";

type RssDefinition = Extract<PortalDefinition, { kind: "rss" }>;
export type CompanyInTitle = NonNullable<RssDefinition["company_in_title"]>;

/** How a feed's titles carry the company, shown with an example title. */
export const COMPANY_IN_TITLE: Record<CompanyInTitle, string> = {
  none: "Not in the title",
  prefix_colon: "Company: Job title",
  suffix_comma: "Job title, Company",
  suffix_at: "Job title at Company",
};

export const COMPANY_IN_TITLE_IDS = Object.keys(COMPANY_IN_TITLE) as CompanyInTitle[];

export function isCompanyInTitle(value: string): value is CompanyInTitle {
  return value in COMPANY_IN_TITLE;
}

export type AtsId = "greenhouse" | "lever" | "ashby" | "workable" | "smartrecruiters";

export const ATS_NAMES: Record<AtsId, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workable: "Workable",
  smartrecruiters: "SmartRecruiters",
};

export const ATS_IDS = Object.keys(ATS_NAMES) as AtsId[];

export function isAts(value: string): value is AtsId {
  return value in ATS_NAMES;
}

// Same rule as the backend (slugs go into ATS URL paths).
const SLUG = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

// Public board URLs people copy from a careers page, and the ATS each one belongs to.
const BOARD_URLS: [RegExp, AtsId][] = [
  [/^(?:job-)?boards(?:\.eu)?\.greenhouse\.io$/, "greenhouse"],
  [/^boards-api\.greenhouse\.io$/, "greenhouse"],
  [/^jobs(?:\.eu)?\.lever\.co$/, "lever"],
  [/^jobs\.ashbyhq\.com$/, "ashby"],
  [/^apply\.workable\.com$/, "workable"],
  [/^(?:jobs|careers)\.smartrecruiters\.com$/, "smartrecruiters"],
];

const ATS_DOMAIN =
  /\.(?:greenhouse\.io|lever\.co|ashbyhq\.com|workable\.com|smartrecruiters\.com)$/i;

export interface CompanyEntry {
  ats: AtsId;
  slug: string;
}

export interface ParsedList {
  entries: CompanyEntry[];
  invalid: string[];
}

function fromUrl(text: string): CompanyEntry | null | "invalid" {
  let url: URL;
  try {
    url = new URL(/^https?:\/\//i.test(text) ? text : `https://${text}`);
  } catch {
    return "invalid";
  }
  const host = url.hostname.toLowerCase();
  const parts = url.pathname.split("/").filter(Boolean);
  const workable = /^([a-z0-9][a-z0-9-]*)\.workable\.com$/.exec(host);
  if (workable?.[1] && workable[1] !== "apply" && workable[1] !== "www") {
    return { ats: "workable", slug: workable[1] };
  }
  for (const [pattern, ats] of BOARD_URLS) {
    if (!pattern.test(host)) continue;
    // boards-api.greenhouse.io/v1/boards/<slug>/jobs; every other board is /<slug>/...
    const slug = host.startsWith("boards-api.") ? parts[2] : parts[0];
    return slug && SLUG.test(slug) ? { ats, slug } : "invalid";
  }
  return null; // not a known board URL
}

/**
 * Board links or bare slugs, one per line (commas and spaces also separate). Links decide
 * their own ATS; bare slugs use `fallback`. Duplicates and a CSV `slug` header are dropped.
 */
export function parseCompanyList(text: string, fallback: AtsId): ParsedList {
  const entries: CompanyEntry[] = [];
  const invalid: string[] = [];
  const seen = new Set<string>();
  for (const raw of text.split(/[\s,;]+/)) {
    const item = raw.trim().replace(/^["']|["']$/g, "");
    if (!item || item.toLowerCase() === "slug") continue;
    // Slugs never contain "/", so anything with one (or an ATS domain) is a link.
    const isLink = item.includes("/") || ATS_DOMAIN.test(item);
    const entry = isLink
      ? (fromUrl(item) ?? "invalid")
      : SLUG.test(item)
        ? { ats: fallback, slug: item }
        : "invalid";
    if (entry === "invalid") {
      invalid.push(item);
      continue;
    }
    const key = `${entry.ats}:${entry.slug.toLowerCase()}`;
    if (!seen.has(key)) {
      seen.add(key);
      entries.push(entry);
    }
  }
  return { entries, invalid };
}

/** "acme-corp" -> "Acme Corp": a readable name until the company's own name is known. */
export function displayName(slug: string): string {
  return slug
    .split(/[-_.]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** "US only", "19 countries", or null for worldwide sources. */
export function coverage(countries: string[]): string | null {
  if (countries.includes("*")) return null;
  if (countries.length === 1 && countries[0]) return `${countries[0]} only`;
  return `${String(countries.length)} countries`;
}

export const FIELD_LABELS: Record<string, string> = {
  app_id: "App ID",
  app_key: "App key",
  api_key: "API key",
  email: "Email the key was issued to",
};

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field.replace(/_/g, " ");
}
