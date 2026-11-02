import {
  BookmarkIcon,
  CompassIcon,
  EyeOffIcon,
  PlusIcon,
  SearchIcon,
  SearchXIcon,
  SparklesIcon,
  Undo2Icon,
  XIcon,
} from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useDismissJobs,
  useInvalidateJobs,
  useJobs,
  usePortals,
  useSaveJobs,
  type JobFilters,
} from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ApplyDialog } from "@/features/applications/ApplyDialog";
import { AddJobDialog } from "@/features/discover/AddJobDialog";
import { TableSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useEventStream } from "@/features/events/EventStreamProvider";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  DEFAULT_FILTERS,
  isFiltered,
  MIN_SCORES,
  selectionText,
  SHOW_OPTIONS,
  showValue,
  STRONG_FIT,
} from "./discoverText";
import { JobDetailSheet } from "./JobDetailSheet";
import { JobTable } from "./JobTable";
import { RankDialog } from "./RankDialog";
import { PRODUCT_NAME } from "@/lib/brand";

const SEARCH_DEBOUNCE_MS = 300;

function useRankProgress() {
  const { tasks } = useEventStream();
  const invalidate = useInvalidateJobs();
  const running = tasks.find(
    (t) => t.kind === "rank" && (t.status === "queued" || t.status === "running"),
  );
  const watching = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (watching.current && watching.current !== running?.id) invalidate();
    watching.current = running?.id;
  }, [running?.id, invalidate]);
  return running;
}

function Filters({
  filters,
  onChange,
}: {
  filters: JobFilters;
  onChange: (next: JobFilters) => void;
}) {
  const portals = usePortals();
  const [search, setSearch] = useState(filters.q ?? "");
  const id = useId();
  const ids = {
    search: `${id}-search`,
    show: `${id}-show`,
    score: `${id}-score`,
    source: `${id}-source`,
    sort: `${id}-sort`,
  };
  const latest = useRef({ filters, onChange });
  useEffect(() => {
    latest.current = { filters, onChange };
  });

  useEffect(() => {
    const timer = setTimeout(() => {
      const { filters: current, onChange: apply } = latest.current;
      if ((current.q ?? "") !== search.trim()) apply({ ...current, q: search.trim() || null });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [search]);

  const minScore = MIN_SCORES.find((m) => m.score === (filters.min_score ?? null))?.value ?? "any";

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="min-w-48 flex-1 space-y-1.5">
        <Label htmlFor={ids.search} className="text-xs">
          Search
        </Label>
        <div className="relative">
          <SearchIcon
            className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            id={ids.search}
            type="search"
            className="pl-8"
            autoComplete="off"
            placeholder="Title, company, or words in the posting"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={ids.show} className="text-xs">
          Show
        </Label>
        <Select
          value={showValue(filters)}
          onValueChange={(value) => {
            const option = SHOW_OPTIONS.find((o) => o.value === value);
            if (option) onChange({ ...filters, ...option.filters });
          }}
        >
          <SelectTrigger id={ids.show} className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SHOW_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={ids.score} className="text-xs">
          Fit
        </Label>
        <Select
          value={minScore}
          onValueChange={(value) => {
            const option = MIN_SCORES.find((m) => m.value === value);
            onChange({ ...filters, min_score: option?.score ?? null });
          }}
        >
          <SelectTrigger id={ids.score} className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MIN_SCORES.map((m) => (
              <SelectItem key={m.value} value={m.value}>
                {m.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={ids.source} className="text-xs">
          Source
        </Label>
        <Select
          value={filters.portal_id ?? "all"}
          onValueChange={(value) => {
            onChange({ ...filters, portal_id: value === "all" ? null : value });
          }}
        >
          <SelectTrigger id={ids.source} className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All sources</SelectItem>
            {(portals.data ?? []).map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={ids.sort} className="text-xs">
          Sort
        </Label>
        <Select
          value={filters.sort ?? "score"}
          onValueChange={(value) => {
            onChange({ ...filters, sort: value === "newest" ? "newest" : "score" });
          }}
        >
          <SelectTrigger id={ids.sort} className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="score">Best fit</SelectItem>
            <SelectItem value="newest">Newest</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex h-9 flex-wrap items-center gap-2">
        <FilterPill
          pressed={filters.min_score === STRONG_FIT}
          onToggle={(on) => {
            onChange({ ...filters, min_score: on ? STRONG_FIT : null });
          }}
        >
          Strong fits only
        </FilterPill>
        <FilterPill
          pressed={filters.remote ?? false}
          onToggle={(remote) => {
            onChange({ ...filters, remote });
          }}
        >
          Remote only
        </FilterPill>
      </div>
    </div>
  );
}

/** The design's toggle pill: ink when on, a card with a hairline when off. */
function FilterPill({
  pressed,
  onToggle,
  children,
}: {
  pressed: boolean;
  onToggle: (pressed: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={() => {
        onToggle(!pressed);
      }}
      className={cn(
        "h-9 cursor-pointer rounded-full px-[13px] text-sm font-medium transition-colors",
        pressed
          ? "bg-foreground text-background shadow-[0_0_0_1px_var(--foreground)]"
          : "bg-card text-foreground shadow-[0_0_0_1px_var(--border)] hover:bg-accent",
      )}
    >
      {children}
    </button>
  );
}

function BulkBar({
  ids,
  dismissedView,
  onRank,
  onClear,
}: {
  ids: number[];
  dismissedView: boolean;
  onRank: () => void;
  onClear: () => void;
}) {
  const save = useSaveJobs();
  const dismiss = useDismissJobs();
  const busy = save.isPending || dismiss.isPending;
  const onError = (error: unknown) => toast.error(errorText(error, "Couldn't update the jobs"));
  return (
    <div
      role="toolbar"
      aria-label="Selected jobs"
      className="flex flex-wrap items-center gap-2 rounded-lg bg-card px-3 py-2 shadow-card"
    >
      <span className="mr-auto text-sm font-medium" aria-live="polite">
        {selectionText(ids.length)}
      </span>
      <Button
        size="sm"
        disabled={busy}
        onClick={() => {
          save.mutate(
            { ids },
            {
              onSuccess: (r) => {
                toast.success(`Saved ${plural(r.changed, "job")} to your pipeline`);
                onClear();
              },
              onError,
            },
          );
        }}
      >
        <BookmarkIcon /> Save
      </Button>
      {dismissedView ? (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => {
            dismiss.mutate({ ids, dismissed: false }, { onSuccess: onClear, onError });
          }}
        >
          <Undo2Icon /> Restore
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => {
            dismiss.mutate(
              { ids },
              {
                onSuccess: (r) => {
                  toast(`Dismissed ${plural(r.changed, "job")}`);
                  onClear();
                },
                onError,
              },
            );
          }}
        >
          <EyeOffIcon /> Dismiss
        </Button>
      )}
      <Button size="sm" variant="outline" disabled={busy} onClick={onRank}>
        <SparklesIcon /> Rank
      </Button>
      <Button size="icon" variant="ghost" aria-label="Clear selection" onClick={onClear}>
        <XIcon />
      </Button>
    </div>
  );
}

export default function DiscoverPage() {
  const [filters, setFilters] = useState<JobFilters>(DEFAULT_FILTERS);
  const jobs = useJobs(filters);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [openId, setOpenId] = useState<number | null>(null);
  const [rank, setRank] = useState<{ jobIds?: number[] } | null>(null);
  const [applyId, setApplyId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const running = useRankProgress();

  const rows = useMemo(() => jobs.data?.pages.flatMap((p) => p.items) ?? [], [jobs.data]);
  const first = jobs.data?.pages[0];
  const changeFilters = useCallback((next: JobFilters) => {
    setFilters(next);
    setSelected(new Set());
  }, []);
  const loadMore = useCallback(() => {
    void jobs.fetchNextPage();
  }, [jobs]);

  if (jobs.isPending) return <TableSkeleton />;

  const stats = first?.stats;
  const header = (
    <PageHeader
      title="Discover"
      description={
        stats && stats.jobs > 0 ? (
          <>
            Ranked against your profile.{" "}
            <b className="font-semibold text-foreground">{plural(stats.jobs, "job")}</b> to review.
          </>
        ) : (
          "Jobs ranked by how well they fit you."
        )
      }
      actions={
        <>
          <Button
            variant="outline"
            onClick={() => {
              setAdding(true);
            }}
          >
            <PlusIcon /> Add a job
          </Button>
          {stats && stats.unranked > 0 && !running && (
            <Button
              onClick={() => {
                setRank({});
              }}
            >
              <SparklesIcon /> Rank {plural(stats.unranked, "new job")}
            </Button>
          )}
        </>
      }
    />
  );
  const addJob = (
    <AddJobDialog
      open={adding}
      onOpenChange={setAdding}
      onAdded={(added) => {
        toast(
          added.created
            ? `Added ${added.title} at ${added.company}.`
            : `${added.title} at ${added.company} is already in your list.`,
        );
        setOpenId(added.job_id);
      }}
    />
  );

  if (jobs.isError) {
    return (
      <>
        {header}
        <EmptyState
          icon={SearchXIcon}
          title="Couldn't load jobs"
          description={errorText(jobs.error, `The ${PRODUCT_NAME} backend didn't answer.`)}
        />
      </>
    );
  }

  if (stats && stats.jobs === 0 && stats.dismissed === 0) {
    return (
      <>
        {header}
        <EmptyState
          icon={CompassIcon}
          title="No jobs to review yet"
          description="Once sources run, ranked jobs appear here with fit scores, reasons, and gaps."
          steps={[
            {
              title: "Set targets",
              description: "Titles, locations, and your salary floor.",
              action: { label: "Profile", to: "/profile" },
            },
            {
              title: "Search",
              description: "Company boards and job feeds for your country.",
              action: { label: "Sources", to: "/sources" },
            },
            {
              title: "Rank",
              description: "See a cost estimate, then score jobs against your profile.",
              action: { label: "Settings", to: "/settings" },
            },
          ]}
        />
        {addJob}
      </>
    );
  }

  const selectedIds = rows.filter((r) => selected.has(r.id)).map((r) => r.id);
  return (
    <>
      {header}
      <div className="space-y-4 px-5 pb-7 md:px-8">
        <Filters filters={filters} onChange={changeFilters} />
        <div aria-live="polite" className="space-y-2 empty:hidden">
          {running && (
            <div className="space-y-1.5 rounded-lg bg-card p-3 shadow-card">
              <Progress
                value={Math.round((running.progress ?? 0) * 100)}
                aria-label="Ranking progress"
              />
              <p className="text-sm text-muted-foreground">{running.message ?? "Starting…"}</p>
            </div>
          )}
        </div>
        {selectedIds.length > 0 ? (
          <BulkBar
            ids={selectedIds}
            dismissedView={filters.show === "dismissed"}
            onRank={() => {
              setRank({ jobIds: selectedIds });
            }}
            onClear={() => {
              setSelected(new Set());
            }}
          />
        ) : (
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {plural(first?.total ?? 0, "job")}
            {stats &&
              ` · ${stats.ranked.toLocaleString("en")} ranked · ${stats.saved.toLocaleString("en")} saved`}
          </p>
        )}
        {rows.length === 0 ? (
          <EmptyState
            icon={SearchXIcon}
            title="No jobs match"
            description="Try a different search or fewer filters."
          >
            {isFiltered(filters) && (
              <Button
                className="mt-6"
                variant="outline"
                onClick={() => {
                  changeFilters(DEFAULT_FILTERS);
                }}
              >
                Clear filters
              </Button>
            )}
          </EmptyState>
        ) : (
          <JobTable
            rows={rows}
            total={first?.total ?? rows.length}
            selected={selected}
            activeId={openId}
            onToggle={(id) => {
              setSelected((current) => {
                const next = new Set(current);
                if (next.has(id)) next.delete(id);
                else next.add(id);
                return next;
              });
            }}
            onToggleAll={(checked) => {
              setSelected(checked ? new Set(rows.map((r) => r.id)) : new Set());
            }}
            onOpen={setOpenId}
            hasMore={jobs.hasNextPage}
            loadingMore={jobs.isFetchingNextPage}
            onLoadMore={loadMore}
          />
        )}
      </div>
      <JobDetailSheet
        id={openId}
        onClose={() => {
          setOpenId(null);
        }}
        onRank={(id) => {
          setRank({ jobIds: [id] });
        }}
        onApply={(id) => {
          setOpenId(null);
          setApplyId(id);
        }}
      />
      <ApplyDialog
        jobId={applyId}
        onClose={() => {
          setApplyId(null);
        }}
      />
      <RankDialog
        open={rank !== null}
        jobIds={rank?.jobIds}
        onOpenChange={(open) => {
          if (!open) setRank(null);
        }}
        onStarted={() => {
          setSelected(new Set());
          toast("Ranking started. Scores appear here when it finishes.");
        }}
      />
      {addJob}
    </>
  );
}
