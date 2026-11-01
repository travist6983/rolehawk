import { ShieldAlertIcon, ShieldCheckIcon } from "lucide-react";

import type { JobDetail } from "@/api/queries";
import { PRODUCT_NAME } from "@/lib/brand";

type Report = NonNullable<JobDetail["integrity_report"]>;

function Quotes({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <ul className="mt-1 space-y-1">
        {items.map((item) => (
          <li key={item} className="rounded bg-muted px-2 py-1 font-mono text-xs break-words">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** What the integrity check removed from or found in a posting (backend portals/integrity.py). */
export function IntegrityNotice({ report }: { report: Report | null }) {
  if (!report || report.verdict === "clean") return null;

  if (report.verdict === "cleaned") {
    return (
      <details className="rounded-md border px-3 py-2 text-xs text-muted-foreground">
        <summary className="flex cursor-pointer items-center gap-1.5">
          <ShieldCheckIcon aria-hidden className="size-3.5" />
          Hidden text was removed from this posting.
        </summary>
        <div className="mt-2 space-y-2">
          <p>{report.summary}</p>
          <Quotes label="It began" items={report.hidden_excerpts} />
          <Quotes label="Links found only in hidden text" items={report.hidden_urls} />
        </div>
      </details>
    );
  }

  return (
    <section
      aria-label="Posting check"
      className="space-y-2 rounded-md border border-caution/60 p-3 text-sm"
    >
      <p className="flex items-center gap-1.5 font-medium text-caution">
        <ShieldAlertIcon aria-hidden className="size-4" />
        Parts of this posting are aimed at AI tools
      </p>
      <p className="text-xs text-muted-foreground">
        {report.summary} {PRODUCT_NAME} never follows instructions in a posting. Some employers add
        lines like these to spot AI-written applications, so read them and decide for yourself.
      </p>
      <Quotes label="Lines addressed to AI tools" items={report.instruction_lines} />
      <Quotes label="Text spelled in invisible characters" items={report.invisible_text} />
      <Quotes label="Words with look-alike letters" items={report.mixed_script_words} />
      <Quotes label="Hidden text removed" items={report.hidden_excerpts} />
    </section>
  );
}
