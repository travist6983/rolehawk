/** Pure helpers for the Settings screen. */

import type { PortalView } from "@/api/queries";
import { plural } from "@/lib/format";

/** The sources that will actually be contacted: on, with any keys they need. */
export function sourceSummary(portals: PortalView[]): string {
  return portals
    .filter((p) => p.enabled && p.ready)
    .map((p) =>
      p.companies === null ? p.name : `${p.name} (${plural(p.companies, "company", "companies")})`,
    )
    .join(", ");
}
