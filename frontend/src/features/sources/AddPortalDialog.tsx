import {
  CheckCircle2Icon,
  FlaskConicalIcon,
  SearchIcon,
  SparklesIcon,
  XCircleIcon,
} from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useAddCompanies,
  useAddCustomPortal,
  useDraftPortal,
  useInspectPortal,
  useLLMStatus,
  useTestPortal,
  type PortalCandidate,
  type PortalDefinition,
  type PortalTestResult,
} from "@/api/queries";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { safeUrl } from "@/features/discover/discoverText";

import {
  COMPANY_IN_TITLE,
  COMPANY_IN_TITLE_IDS,
  isAts,
  isCompanyInTitle,
  plural,
} from "./sourceText";

function Candidates({
  candidates,
  busy,
  onTest,
  onWatch,
}: {
  candidates: PortalCandidate[];
  busy: boolean;
  onTest: (definition: PortalDefinition) => void;
  onWatch: (candidate: PortalCandidate) => void;
}) {
  return (
    <ul className="space-y-2" aria-label="Ways to read this site">
      {candidates.map((c) => (
        <li key={`${c.kind}-${c.title}`} className="flex items-start gap-3 rounded-lg border p-3">
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-medium">{c.title}</p>
            <p className="break-words text-muted-foreground">{c.detail}</p>
          </div>
          {c.kind === "watchlist" ? (
            <Button
              size="sm"
              disabled={busy}
              onClick={() => {
                onWatch(c);
              }}
            >
              Add to watchlist
            </Button>
          ) : c.definition ? (
            <Button
              size="sm"
              disabled={busy}
              onClick={() => {
                if (c.definition) onTest(c.definition);
              }}
            >
              <FlaskConicalIcon /> Test it
            </Button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function TestReport({ result }: { result: PortalTestResult }) {
  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-sm font-medium" role="status">
        {result.ok ? (
          <CheckCircle2Icon className="size-4 text-score-high" aria-hidden />
        ) : (
          <XCircleIcon className="size-4 text-destructive" aria-hidden />
        )}
        {result.ok
          ? `Found ${plural(result.count, "job")}. Here are the first few.`
          : (result.error ?? "The test run failed.")}
      </p>
      {result.samples.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs text-muted-foreground">
              <th scope="col" className="py-1 font-medium">
                Title
              </th>
              <th scope="col" className="py-1 font-medium">
                Company
              </th>
              <th scope="col" className="py-1 font-medium">
                Location
              </th>
            </tr>
          </thead>
          <tbody>
            {result.samples.map((job) => {
              const link = safeUrl(job.url);
              return (
                <tr key={job.external_id} className="border-t">
                  <td className="py-1 pr-2">
                    {link ? (
                      <a
                        href={link}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-primary-text underline-offset-4 hover:underline"
                      >
                        {job.title}
                      </a>
                    ) : (
                      job.title
                    )}
                  </td>
                  <td className="py-1 pr-2">{job.company || "–"}</td>
                  <td className="py-1">{job.location ?? "–"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {result.errors.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {plural(result.errors.length, "page")} couldn't be read: {result.errors[0]}
        </p>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground select-none">
          Plugin file it will create
        </summary>
        <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-muted p-3 font-mono text-xs leading-relaxed">
          <code>{result.plugin_source}</code>
        </pre>
      </details>
    </div>
  );
}

export function AddPortalDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [url, setUrl] = useState("");
  const [definition, setDefinition] = useState<PortalDefinition | null>(null);
  const inspect = useInspectPortal();
  const draft = useDraftPortal();
  const test = useTestPortal();
  const add = useAddCustomPortal();
  const addCompanies = useAddCompanies();
  const status = useLLMStatus();
  const urlId = useId();
  const nameId = useId();
  const companyId = useId();
  const busy = inspect.isPending || draft.isPending || test.isPending || add.isPending;

  const reset = () => {
    setDefinition(null);
    inspect.reset();
    draft.reset();
    test.reset();
  };
  const close = () => {
    reset();
    setUrl("");
    onOpenChange(false);
  };
  const runTest = (d: PortalDefinition) => {
    setDefinition(d);
    test.mutate(d, {
      // The run can settle details (how feed titles carry the company); add what was tested.
      onSuccess: (result) => {
        setDefinition(result.definition);
      },
      onError: (error) => toast.error(errorText(error, "Couldn't test the source")),
    });
  };
  const candidates = [...(inspect.data?.candidates ?? []), ...(draft.data ? [draft.data] : [])];
  const nothingFound = inspect.data !== undefined && !inspect.data.error && candidates.length === 0;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a job site</DialogTitle>
          <DialogDescription>
            Paste a company's careers page or a job board. Offerbound looks for a feed or structured
            job data first and only falls back to reading the page layout. You see sample jobs and
            the plugin file before anything is added.
          </DialogDescription>
        </DialogHeader>

        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            reset();
            inspect.mutate(url.trim(), {
              onError: (error) => toast.error(errorText(error, "Couldn't open that page")),
            });
          }}
        >
          <div className="min-w-60 flex-1 space-y-1.5">
            <Label htmlFor={urlId}>Careers page URL</Label>
            <Input
              id={urlId}
              type="url"
              required
              placeholder="https://example.com/careers"
              value={url}
              onChange={(event) => {
                setUrl(event.target.value);
              }}
            />
          </div>
          <Button type="submit" disabled={busy || !url.trim()}>
            <SearchIcon /> {inspect.isPending ? "Looking…" : "Look at this page"}
          </Button>
        </form>

        {inspect.data?.error && (
          <p className="text-sm text-destructive" role="alert">
            {inspect.data.error}
          </p>
        )}
        {candidates.length > 0 && !test.data && (
          <Candidates
            candidates={candidates}
            busy={busy}
            onTest={runTest}
            onWatch={(c) => {
              if (!c.ats || !c.slug || !isAts(c.ats)) return;
              addCompanies.mutate(
                { ats: c.ats, companies: [{ slug: c.slug }] },
                {
                  onSuccess: () => {
                    toast.success(`Added ${c.slug} to your watchlist`);
                    close();
                  },
                  onError: (error) => toast.error(errorText(error, "Couldn't add it")),
                },
              );
            }}
          />
        )}
        {nothingFound && !draft.data && (
          <div className="space-y-2 rounded-lg border border-dashed p-3 text-sm">
            <p>No feed or structured job data on this page.</p>
            {status.data?.configured ? (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => {
                  draft.mutate(
                    { url: url.trim() },
                    {
                      onError: (error) =>
                        toast.error(errorText(error, "Claude couldn't read this page")),
                    },
                  );
                }}
              >
                <SparklesIcon />{" "}
                {draft.isPending ? "Reading the page…" : "Ask Claude to read the layout"}
              </Button>
            ) : (
              <p className="text-muted-foreground">
                Connect Claude in Settings (or use the /add-portal skill in Claude Code) to have it
                read the page layout.
              </p>
            )}
          </div>
        )}
        {test.isPending && <p className="text-sm text-muted-foreground">Test run in progress…</p>}
        {test.data && definition && (
          <>
            <TestReport result={test.data} />
            {test.data.ok && (
              <div className="flex flex-wrap gap-3">
                <div className="min-w-48 flex-1 space-y-1.5">
                  <Label htmlFor={nameId}>Name</Label>
                  <Input
                    id={nameId}
                    maxLength={80}
                    value={definition.name}
                    onChange={(event) => {
                      setDefinition({ ...definition, name: event.target.value });
                    }}
                  />
                </div>
                {definition.kind === "rss" && (
                  <div className="space-y-1.5">
                    <Label htmlFor={companyId}>Company in job titles</Label>
                    <Select
                      value={definition.company_in_title ?? "none"}
                      disabled={busy}
                      onValueChange={(value) => {
                        if (isCompanyInTitle(value)) {
                          runTest({ ...definition, company_in_title: value });
                        }
                      }}
                    >
                      <SelectTrigger id={companyId} className="w-52">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {COMPANY_IN_TITLE_IDS.map((id) => (
                          <SelectItem key={id} value={id}>
                            {COMPANY_IN_TITLE[id]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        <DialogFooter>
          {test.data && (
            <Button variant="ghost" disabled={busy} onClick={reset}>
              Back
            </Button>
          )}
          <Button variant="outline" onClick={close}>
            Cancel
          </Button>
          {test.data?.ok && definition && (
            <Button
              disabled={busy || !definition.name.trim()}
              onClick={() => {
                add.mutate(definition, {
                  onSuccess: (portal) => {
                    toast.success(`${portal.name} added. It runs with your next search.`);
                    close();
                  },
                  onError: (error) => toast.error(errorText(error, "Couldn't add the source")),
                });
              }}
            >
              {add.isPending ? "Testing again and adding…" : "Add source"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
