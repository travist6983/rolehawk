import { observeElementRect, useVirtualizer, type Virtualizer } from "@tanstack/react-virtual";
import { BookmarkIcon, ShieldAlertIcon } from "lucide-react";
import { useEffect, useRef } from "react";

import type { JobRow } from "@/api/queries";
import { FitRuler } from "@/components/ScoreBadge";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

import { OUTSIDE_TEXT, deadlineText, gateNote, staleText, whereText } from "./discoverText";

const ROW_HEIGHT = 66;
const LOAD_MORE_WITHIN = 30; // rows from the end
// A container that measures 0 (hidden, or jsdom in tests) still renders a screenful of rows.
const FALLBACK_RECT = { width: 1024, height: 900 };

function observeWithFallback(
  instance: Virtualizer<HTMLDivElement, Element>,
  callback: (rect: { width: number; height: number }) => void,
) {
  return observeElementRect(instance, (rect) => {
    callback(rect.height > 0 ? rect : FALLBACK_RECT);
  });
}

interface JobTableProps {
  rows: JobRow[];
  total: number;
  selected: ReadonlySet<number>;
  activeId: number | null;
  onToggle: (id: number) => void;
  onToggleAll: (checked: boolean) => void;
  onOpen: (id: number) => void;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
}

export function JobTable({
  rows,
  total,
  selected,
  activeId,
  onToggle,
  onToggleAll,
  onOpen,
  hasMore,
  loadingMore,
  onLoadMore,
}: JobTableProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Virtual returns new functions each render by design; the compiler just skips memoizing this component
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
    observeElementRect: observeWithFallback,
  });
  const items = virtualizer.getVirtualItems();
  const last = items.at(-1)?.index ?? 0;

  useEffect(() => {
    if (hasMore && !loadingMore && last >= rows.length - LOAD_MORE_WITHIN) onLoadMore();
  }, [hasMore, loadingMore, last, rows.length, onLoadMore]);

  const paddingTop = items[0]?.start ?? 0;
  const paddingBottom = virtualizer.getTotalSize() - (items.at(-1)?.end ?? 0);
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.id));
  const someChecked = !allChecked && rows.some((r) => selected.has(r.id));

  return (
    <div ref={scrollRef} className="h-[calc(100dvh-17rem)] min-h-80 overflow-auto" tabIndex={-1}>
      <table className="w-full table-fixed text-sm" aria-rowcount={total + 1}>
        <thead className="sticky top-0 z-10 bg-background shadow-[inset_0_-1px_0_var(--foreground)]">
          <tr className="text-left text-[13px] text-muted-foreground" aria-rowindex={1}>
            <th scope="col" className="w-10 px-3 py-2">
              <Checkbox
                aria-label="Select all loaded jobs"
                checked={allChecked ? true : someChecked ? "indeterminate" : false}
                onCheckedChange={(checked) => {
                  onToggleAll(checked === true);
                }}
              />
            </th>
            <th scope="col" className="w-36 py-2 pr-4 font-medium">
              Fit
            </th>
            <th scope="col" className="py-2 font-medium">
              Role
            </th>
            <th scope="col" className="hidden w-56 py-2 font-medium md:table-cell">
              Location
            </th>
            <th scope="col" className="hidden w-44 py-2 font-medium xl:table-cell">
              Salary
            </th>
            <th scope="col" className="hidden w-36 py-2 font-medium lg:table-cell">
              Source
            </th>
            <th scope="col" className="hidden w-28 py-2 pr-3 font-medium sm:table-cell">
              Posted
            </th>
          </tr>
        </thead>
        <tbody>
          {paddingTop > 0 && <tr aria-hidden style={{ height: paddingTop }} />}
          {items.map((item) => {
            const job = rows[item.index];
            if (!job) return null;
            const checked = selected.has(job.id);
            const gate = gateNote(job);
            return (
              <tr
                key={job.id}
                aria-rowindex={item.index + 2}
                style={{ height: ROW_HEIGHT }}
                className={cn(
                  "cursor-pointer border-b hover:bg-accent",
                  checked && "bg-accent",
                  activeId === job.id && "bg-accent shadow-[inset_3px_0_0_var(--primary)]",
                )}
                onClick={() => {
                  onOpen(job.id);
                }}
              >
                <td
                  className="px-3"
                  onClick={(event) => {
                    event.stopPropagation();
                  }}
                >
                  <Checkbox
                    aria-label={`Select ${job.title} at ${job.company}`}
                    checked={checked}
                    onCheckedChange={() => {
                      onToggle(job.id);
                    }}
                  />
                </td>
                <td className="pr-4">
                  {job.score !== null ? (
                    <FitRuler score={job.score} />
                  ) : (
                    <span className="text-xs text-muted-foreground" title="Not ranked yet">
                      –
                    </span>
                  )}
                </td>
                <td className="min-w-0 pr-3">
                  <button
                    type="button"
                    className="block max-w-full truncate text-left font-serif text-[17px] leading-tight font-medium hover:underline focus-visible:underline focus-visible:outline-none"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpen(job.id);
                    }}
                  >
                    {job.title}
                  </button>
                  <span className="flex items-center gap-1.5 truncate text-[13.5px] text-foreground-2">
                    {job.company}
                    {job.stage && (
                      <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">
                        <BookmarkIcon aria-hidden />{" "}
                        {job.stage === "saved" ? "Saved" : "In pipeline"}
                      </Badge>
                    )}
                    {gate && (
                      <span
                        className={cn(
                          "shrink-0 text-[10px] font-medium",
                          gate.fail ? "text-destructive" : "text-caution",
                        )}
                      >
                        {gate.label}
                      </span>
                    )}
                    {job.outside_preferences && (
                      <span
                        className="shrink-0 text-[10px] font-medium text-muted-foreground"
                        title="Outside your preferences, so ranking skips it unless you pick it and rank it anyway"
                      >
                        {OUTSIDE_TEXT[job.outside_preferences]}
                      </span>
                    )}
                    {job.integrity === "warning" && (
                      <span
                        className="flex shrink-0 items-center gap-0.5 text-caution"
                        title="Parts of this posting are aimed at AI tools"
                      >
                        <ShieldAlertIcon aria-hidden className="size-3" />
                        <span className="sr-only">Parts of this posting are aimed at AI tools</span>
                      </span>
                    )}
                    <span className="truncate md:hidden">· {whereText(job)}</span>
                  </span>
                </td>
                <td className="hidden truncate pr-3 md:table-cell">{whereText(job)}</td>
                <td className="hidden truncate pr-3 tabular-nums xl:table-cell">
                  {job.salary_text ?? "–"}
                </td>
                <td className="hidden truncate pr-3 text-foreground-2 lg:table-cell">
                  {job.source}
                </td>
                <td className="hidden pr-3 text-foreground-2 sm:table-cell">
                  {job.deadline ? (
                    <span className={job.deadline === "soon" ? "font-medium text-caution" : ""}>
                      {deadlineText(job)}
                    </span>
                  ) : (
                    <span
                      className={job.stale_days !== null ? "text-caution" : undefined}
                      title={
                        job.stale_days !== null
                          ? `${staleText(job) ?? ""}. Some stay open for months; check before applying.`
                          : undefined
                      }
                    >
                      {timeAgo(job.posted_at ?? job.scraped_at)}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
          {paddingBottom > 0 && <tr aria-hidden style={{ height: paddingBottom }} />}
        </tbody>
      </table>
      {loadingMore && (
        <p className="py-3 text-center text-xs text-muted-foreground">Loading more jobs…</p>
      )}
    </div>
  );
}
