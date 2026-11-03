import { Building2Icon, Loader2Icon, PlusIcon, SearchIcon, Trash2Icon } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useAddCompanies,
  useCheckCompany,
  useCompanies,
  useRemoveCompany,
  useSetCompanyEnabled,
  useSwitchCompanies,
  type CompanyView,
} from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import {
  ATS_IDS,
  ATS_NAMES,
  displayName,
  isAts,
  parseCompanyList,
  plural,
  type AtsId,
  type CompanyEntry,
} from "./sourceText";

const CHECK_CONCURRENCY = 3;

interface ImportOutcome {
  entry: CompanyEntry;
  ok: boolean;
  text: string;
}

function CompanyRow({ company }: { company: CompanyView }) {
  const toggle = useSetCompanyEnabled();
  const remove = useRemoveCompany();
  const switchId = useId();
  const atsName = isAts(company.ats) ? ATS_NAMES[company.ats] : company.ats;
  return (
    <li className="flex items-center gap-3 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <Label htmlFor={switchId} className="block truncate font-medium">
          {company.name}
        </Label>
        <p className="truncate text-xs text-muted-foreground">
          <span>{atsName}</span>
          {" · "}
          <span className="font-mono">{company.slug}</span>
          {company.industry && ` · ${company.industry}`}
        </p>
      </div>
      <span className="hidden shrink-0 text-right text-xs sm:block">
        {company.last_error ? (
          <span className="text-destructive">{company.last_error}</span>
        ) : company.last_job_count !== null ? (
          <span className="text-muted-foreground">
            {plural(company.last_job_count, "open job")}
          </span>
        ) : null}
      </span>
      {company.source === "user" && <Badge variant="secondary">Added by you</Badge>}
      <Switch
        id={switchId}
        checked={company.enabled}
        disabled={toggle.isPending}
        onCheckedChange={(enabled) => {
          toggle.mutate(
            { id: company.id, enabled },
            { onError: (error) => toast.error(errorText(error, "Couldn't update the company")) },
          );
        }}
      />
      {company.source === "user" && (
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Remove ${company.name}`}
          disabled={remove.isPending}
          onClick={() => {
            remove.mutate(company.id, {
              onSuccess: () => toast(`${company.name} removed`),
              onError: (error) => toast.error(errorText(error, "Couldn't remove the company")),
            });
          }}
        >
          <Trash2Icon />
        </Button>
      )}
    </li>
  );
}

function ImportForm() {
  const [text, setText] = useState("");
  const [fallback, setFallback] = useState<AtsId>("greenhouse");
  const [busy, setBusy] = useState(false);
  const [outcomes, setOutcomes] = useState<ImportOutcome[]>([]);
  const [invalid, setInvalid] = useState<string[]>([]);
  const check = useCheckCompany();
  const add = useAddCompanies();
  const textId = useId();
  const atsId = useId();

  const run = async () => {
    const parsed = parseCompanyList(text, fallback);
    setInvalid(parsed.invalid);
    setOutcomes([]);
    if (parsed.entries.length === 0) return;
    setBusy(true);
    const results: ImportOutcome[] = [];
    const names = new Map<CompanyEntry, string>();
    const queue = [...parsed.entries];
    const worker = async () => {
      for (let entry = queue.shift(); entry; entry = queue.shift()) {
        try {
          const found = await check.mutateAsync({ ats: entry.ats, slug: entry.slug });
          if (found.ok) {
            const name = found.company ?? displayName(entry.slug);
            names.set(entry, name);
            results.push({ entry, ok: true, text: `${name}: ${plural(found.jobs, "open job")}` });
          } else {
            results.push({ entry, ok: false, text: found.detail ?? "Not found" });
          }
        } catch (error) {
          results.push({ entry, ok: false, text: errorText(error, "Couldn't check") });
        }
      }
    };
    try {
      await Promise.all(Array.from({ length: CHECK_CONCURRENCY }, worker));
      const found = parsed.entries.filter((e) => names.has(e));
      for (const ats of ATS_IDS) {
        const companies = found
          .filter((e) => e.ats === ats)
          .map((e) => ({ slug: e.slug, name: names.get(e) ?? null }));
        if (companies.length > 0) await add.mutateAsync({ ats, companies });
      }
      if (found.length > 0) {
        toast.success(`Added ${plural(found.length, "company", "companies")} to the watchlist`);
        setText("");
      }
    } catch (error) {
      toast.error(errorText(error, "Couldn't add the companies"));
    } finally {
      // Same order the user pasted them in.
      const order = new Map(parsed.entries.map((e, i) => [e, i]));
      setOutcomes(results.sort((a, b) => (order.get(a.entry) ?? 0) - (order.get(b.entry) ?? 0)));
      setBusy(false);
    }
  };

  return (
    <form
      className="space-y-3 rounded-lg border bg-muted/30 p-4"
      aria-label="Add companies"
      onSubmit={(event) => {
        event.preventDefault();
        void run();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor={textId}>Add companies</Label>
        <Textarea
          id={textId}
          rows={3}
          spellCheck={false}
          placeholder={"https://boards.greenhouse.io/stripe\nhttps://jobs.lever.co/plaid\nnotion"}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
        <p className="text-xs text-muted-foreground">
          Paste careers-page links (Greenhouse, Lever, Ashby, Workable, SmartRecruiters) or board
          names, one per line. Each one is checked before it's added.
        </p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor={atsId} className="text-xs">
            Board names are on
          </Label>
          <Select
            value={fallback}
            onValueChange={(value) => {
              if (isAts(value)) setFallback(value);
            }}
          >
            <SelectTrigger id={atsId} className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ATS_IDS.map((ats) => (
                <SelectItem key={ats} value={ats}>
                  {ATS_NAMES[ats]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button type="submit" disabled={busy || text.trim() === ""}>
          {busy ? (
            <Loader2Icon className="animate-spin motion-reduce:animate-none" />
          ) : (
            <PlusIcon />
          )}
          {busy ? "Checking…" : "Check and add"}
        </Button>
      </div>
      <div aria-live="polite" className="space-y-1 text-sm empty:hidden">
        {outcomes.map((o) => (
          <p key={`${o.entry.ats}:${o.entry.slug}`} className={o.ok ? "" : "text-destructive"}>
            <span className="font-mono text-xs">{o.entry.slug}</span>{" "}
            <span className="text-muted-foreground">({ATS_NAMES[o.entry.ats]})</span>: {o.text}
          </p>
        ))}
        {invalid.length > 0 && (
          <p className="text-destructive">Not a board link or name: {invalid.join(", ")}</p>
        )}
      </div>
    </form>
  );
}

export function Watchlist({
  filter,
  onFilterChange,
}: {
  filter: string;
  onFilterChange: (ats: string) => void;
}) {
  const companies = useCompanies();
  const [query, setQuery] = useState("");
  const filterId = useId();
  const searchId = useId();

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (companies.data ?? []).filter(
      (c) =>
        (filter === "all" || c.ats === filter) &&
        (!needle ||
          c.name.toLowerCase().includes(needle) ||
          c.slug.toLowerCase().includes(needle) ||
          (c.industry ?? "").toLowerCase().includes(needle)),
    );
  }, [companies.data, filter, query]);
  const enabled = visible.filter((c) => c.enabled).length;
  const switchAll = useSwitchCompanies();

  return (
    <Card aria-labelledby={`${filterId}-title`}>
      <CardHeader>
        <CardTitle id={`${filterId}-title`} className="flex items-center gap-2">
          <Building2Icon className="size-5 text-muted-foreground" aria-hidden /> Company watchlist
        </CardTitle>
        <CardDescription>
          Company job boards are searched one company at a time. Switch off companies you don't
          want, or add the ones you'd love to work for.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ImportForm />
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5">
            <Label htmlFor={filterId} className="text-xs">
              Job board
            </Label>
            <Select value={filter} onValueChange={onFilterChange}>
              <SelectTrigger id={filterId} className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All boards</SelectItem>
                {ATS_IDS.map((ats) => (
                  <SelectItem key={ats} value={ats}>
                    {ATS_NAMES[ats]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-48 flex-1 space-y-1.5">
            <Label htmlFor={searchId} className="text-xs">
              Find a company
            </Label>
            <div className="relative">
              <SearchIcon
                className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <Input
                id={searchId}
                className="pl-8"
                autoComplete="off"
                placeholder="Name, board name, or industry"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                }}
              />
            </div>
          </div>
          <p className="pb-2 text-sm text-muted-foreground" aria-live="polite">
            {enabled} of {plural(visible.length, "company", "companies")} on
          </p>
          {visible.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              className="mb-1"
              disabled={switchAll.isPending}
              onClick={() => {
                const on = enabled === 0;
                switchAll.mutate(
                  { ids: visible.map((c) => c.id), enabled: on },
                  {
                    onError: (error) =>
                      toast.error(errorText(error, "Couldn't switch the companies")),
                  },
                );
              }}
            >
              {enabled === 0 ? "Switch all on" : "Switch all off"}
            </Button>
          )}
        </div>
        {companies.isPending ? (
          <div className="space-y-2" aria-label="Loading companies">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            {query ? "No companies match." : "No companies yet. Add some above."}
          </p>
        ) : (
          <ul
            aria-label="Companies"
            className="max-h-[28rem] divide-y overflow-y-auto rounded-lg border"
          >
            {visible.map((company) => (
              <CompanyRow key={company.id} company={company} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
