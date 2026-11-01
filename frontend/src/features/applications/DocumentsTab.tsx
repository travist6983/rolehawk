import { AlertTriangleIcon, DownloadIcon, SaveIcon, SparklesIcon, Undo2Icon } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  applicationFileUrl,
  applicationKeys,
  useKeepFlag,
  useRegenerate,
  useSaveDocuments,
  type Bundle,
  type CoverLetter,
  type CvDocument,
  type Flag,
  type RegenerateSection,
} from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { useEventStream } from "@/features/events/EventStreamProvider";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";

import {
  canDrop,
  commaTextToList,
  dropLine,
  FLAG_KINDS,
  flagsAt,
  linesToList,
  listToCommaText,
  sectionFor,
  softenInstruction,
  textToParagraphs,
} from "./applicationText";
import {
  FlagActionsContext,
  RewriteAskContext,
  useFlagActions,
  useRewriteAsk,
  type FlagActions,
  type RewriteAsk,
} from "./flagActions";

export type Doc = "cv" | "cover_letter";

/** A textarea editing a list as text. It keeps the raw text (so a new empty line survives
 * while typing) and reports the parsed list; remount it (key) to load new data. */
function ListTextarea({
  items,
  toText,
  toItems,
  onItems,
  ...props
}: Omit<React.ComponentProps<typeof Textarea>, "value" | "onChange"> & {
  items: string[];
  toText: (items: string[]) => string;
  toItems: (text: string) => string[];
  onItems: (items: string[]) => void;
}) {
  const [text, setText] = useState(() => toText(items));
  return (
    <Textarea
      {...props}
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        onItems(toItems(event.target.value));
      }}
    />
  );
}

const lines = (items: string[]) => items.join("\n");
const paragraphs = (items: string[]) => items.join("\n\n");

function FlagButtons({ flag }: { flag: Flag }) {
  const actions = useFlagActions();
  if (!actions || !["stretch", "style", "unaddressed"].includes(flag.kind)) return null;
  const rewritable = flag.kind !== "unaddressed" && sectionFor(flag) !== null;
  return (
    <span className="mt-1 flex flex-wrap gap-1">
      <Button
        size="sm"
        variant="outline"
        className="h-6 px-2 text-xs"
        disabled={actions.busy}
        onClick={() => {
          actions.keep(flag);
        }}
      >
        Keep as written
      </Button>
      {rewritable && (
        <Button
          size="sm"
          variant="outline"
          className="h-6 px-2 text-xs"
          onClick={() => {
            actions.soften(flag);
          }}
        >
          {flag.kind === "stretch" ? "Soften" : "Rewrite"}
        </Button>
      )}
      {flag.kind === "stretch" && canDrop(flag) && (
        <Button
          size="sm"
          variant="outline"
          className="h-6 px-2 text-xs"
          onClick={() => {
            actions.drop(flag);
          }}
        >
          Drop line
        </Button>
      )}
    </span>
  );
}

function FlagList({ flags }: { flags: Flag[] }) {
  const quote = (text: string) => (text.length > 120 ? `${text.slice(0, 117)}…` : text);
  if (flags.length === 0) return null;
  return (
    <ul className="space-y-1" aria-label="Needs your review">
      {flags.map((f) => {
        const kind = FLAG_KINDS[f.kind];
        return (
          <li
            key={`${f.document}:${f.location}:${f.text}:${f.issue}`}
            className={cn(
              "flex gap-1.5 rounded-md px-2 py-1 text-xs",
              kind.serious ? "bg-destructive/10 text-destructive" : "bg-muted text-caution",
            )}
          >
            <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <span>
              <span className="font-medium">{kind.label}:</span>{" "}
              <span className="font-medium">&ldquo;{quote(f.text)}&rdquo;</span> {f.issue}
              {f.source === "review" && <span className="opacity-80"> (AI review)</span>}
              <FlagButtons flag={f} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Rewrite({
  section,
  applicationId,
  disabled,
}: {
  section: RegenerateSection;
  applicationId: number;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  // A flag's "Soften" asks this section to open its form pre-filled (adjusting state while
  // rendering, as React recommends, rather than in an effect).
  const ask = useRewriteAsk();
  const [seenAsk, setSeenAsk] = useState(ask);
  if (ask !== seenAsk) {
    setSeenAsk(ask);
    if (ask?.section === section) {
      setTaskId(null);
      setInstruction(ask.instruction);
      setOpen(true);
    }
  }
  const regenerate = useRegenerate(applicationId);
  const stream = useEventStream();
  const client = useQueryClient();
  const task = taskId ? stream.task(taskId) : undefined;
  const running = task !== undefined && (task.status === "queued" || task.status === "running");
  const inputId = useId();

  const finished = task?.status === "succeeded" || task?.status === "failed";
  useEffect(() => {
    if (!finished) return;
    void client.invalidateQueries({ queryKey: applicationKeys.detail(applicationId) });
    if (task.status === "failed") toast.error(task.error ?? "Couldn't rewrite it");
  }, [finished, task?.status, task?.error, client, applicationId]);

  if (running) {
    return (
      <div className="w-48 space-y-1" aria-live="polite">
        <Progress value={Math.round((task.progress ?? 0) * 100)} aria-label="Rewriting" />
        <p className="text-xs text-muted-foreground">{task.message ?? "Rewriting…"}</p>
      </div>
    );
  }
  if (!open || finished) {
    return (
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        onClick={() => {
          setTaskId(null);
          setInstruction("");
          setOpen(true);
        }}
      >
        <SparklesIcon /> Rewrite
      </Button>
    );
  }
  return (
    <form
      className="flex w-full flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        regenerate.mutate(
          { section, instruction: instruction.trim() || null },
          {
            onSuccess: (ref) => {
              setTaskId(ref.task_id);
            },
            onError: (error) => toast.error(errorText(error, "Couldn't start the rewrite")),
          },
        );
      }}
    >
      <div className="min-w-48 flex-1 space-y-1">
        <Label htmlFor={inputId} className="text-xs">
          What should change? (optional)
        </Label>
        <Input
          id={inputId}
          value={instruction}
          maxLength={1000}
          placeholder="e.g. lead with the accessibility work"
          onChange={(event) => {
            setInstruction(event.target.value);
          }}
        />
      </div>
      <Button type="submit" size="sm" disabled={regenerate.isPending}>
        <SparklesIcon /> Rewrite with Claude
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => {
          setOpen(false);
        }}
      >
        Cancel
      </Button>
    </form>
  );
}

function Section({
  title,
  flags,
  rewrite,
  children,
}: {
  title: string;
  flags: Flag[];
  rewrite?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className={cn("space-y-2 rounded-lg border p-3", flags.length > 0 && "border-destructive/50")}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium">
          {title}
          {flags.length > 0 && (
            <Badge variant="destructive" className="ml-2">
              {flags.length} to check
            </Badge>
          )}
        </h3>
        {rewrite}
      </div>
      {children}
      <FlagList flags={flags} />
    </section>
  );
}

function CvEditor({
  cv,
  flags,
  applicationId,
  onChange,
  busy,
  version,
}: {
  version: string;
  cv: CvDocument;
  flags: Flag[];
  applicationId: number;
  onChange: (cv: CvDocument) => void;
  busy: boolean;
}) {
  const id = useId();
  const rewrite = (section: RegenerateSection) => (
    <Rewrite section={section} applicationId={applicationId} disabled={busy} />
  );
  return (
    <div className="space-y-3">
      <Section
        title="Summary"
        flags={[...flagsAt(flags, "cv", "headline"), ...flagsAt(flags, "cv", "summary")]}
        rewrite={rewrite("summary")}
      >
        <Label htmlFor={`${id}-headline`} className="text-xs">
          Headline
        </Label>
        <Input
          id={`${id}-headline`}
          value={cv.headline ?? ""}
          onChange={(e) => {
            onChange({ ...cv, headline: e.target.value || null });
          }}
        />
        <Label htmlFor={`${id}-summary`} className="text-xs">
          Summary
        </Label>
        <Textarea
          id={`${id}-summary`}
          rows={4}
          value={cv.summary ?? ""}
          onChange={(e) => {
            onChange({ ...cv, summary: e.target.value || null });
          }}
        />
      </Section>
      <Section title="Experience" flags={[]} rewrite={rewrite("experience")}>
        {cv.experience.map((role, i) => {
          const roleFlags = flagsAt(flags, "cv", `experience.${String(i)}`);
          return (
            <div key={`${role.title}-${role.start ?? i}`} className="space-y-1.5">
              <Label htmlFor={`${id}-role-${String(i)}`} className="text-xs">
                {role.title}
                {role.organization && `, ${role.organization}`}
                <span className="font-normal text-muted-foreground"> (one bullet per line)</span>
              </Label>
              <ListTextarea
                key={version}
                id={`${id}-role-${String(i)}`}
                rows={Math.max(3, role.bullets.length + 1)}
                aria-invalid={roleFlags.length > 0}
                items={role.bullets}
                toText={lines}
                toItems={linesToList}
                onItems={(bullets) => {
                  const experience = cv.experience.map((r, j) => (j === i ? { ...r, bullets } : r));
                  onChange({ ...cv, experience });
                }}
              />
              <FlagList flags={roleFlags} />
            </div>
          );
        })}
      </Section>
      <Section title="Skills" flags={flagsAt(flags, "cv", "skills")} rewrite={rewrite("skills")}>
        <Label htmlFor={`${id}-skills`} className="text-xs">
          Skills, separated by commas
        </Label>
        <ListTextarea
          key={version}
          id={`${id}-skills`}
          rows={2}
          items={cv.skills}
          toText={listToCommaText}
          toItems={commaTextToList}
          onItems={(skills) => {
            onChange({ ...cv, skills });
          }}
        />
      </Section>
      <p className="text-xs text-muted-foreground">
        Employers, titles, dates, education, and certifications always come from your profile.
        Change them there.
      </p>
    </div>
  );
}

function LetterEditor({
  letter,
  flags,
  applicationId,
  onChange,
  busy,
  version,
}: {
  version: string;
  letter: CoverLetter;
  flags: Flag[];
  applicationId: number;
  onChange: (letter: CoverLetter) => void;
  busy: boolean;
}) {
  const id = useId();
  return (
    <Section
      title="Cover letter"
      flags={flagsAt(flags, "cover_letter", "paragraphs")}
      rewrite={<Rewrite section="cover_letter" applicationId={applicationId} disabled={busy} />}
    >
      <Label htmlFor={`${id}-greeting`} className="text-xs">
        Greeting
      </Label>
      <Input
        id={`${id}-greeting`}
        value={letter.greeting}
        onChange={(e) => {
          onChange({ ...letter, greeting: e.target.value });
        }}
      />
      <Label htmlFor={`${id}-body`} className="text-xs">
        Letter (blank line between paragraphs)
      </Label>
      <ListTextarea
        key={version}
        id={`${id}-body`}
        rows={12}
        items={letter.paragraphs}
        toText={paragraphs}
        toItems={textToParagraphs}
        onItems={(items) => {
          onChange({ ...letter, paragraphs: items });
        }}
      />
      <Label htmlFor={`${id}-closing`} className="text-xs">
        Closing
      </Label>
      <Input
        id={`${id}-closing`}
        value={letter.closing}
        onChange={(e) => {
          onChange({ ...letter, closing: e.target.value });
        }}
      />
    </Section>
  );
}

/** Remount with `key={bundle.updated_at}` to load a new bundle (after a save or rewrite). */
export function DocumentsTab({
  applicationId,
  bundle,
  doc,
  onDocChange,
}: {
  applicationId: number;
  bundle: Bundle;
  doc: Doc;
  onDocChange: (doc: Doc) => void;
}) {
  const [cv, setCv] = useState<CvDocument>(bundle.cv);
  const [letter, setLetter] = useState<CoverLetter>(bundle.cover_letter);
  const [resets, setResets] = useState(0);
  const [ask, setAsk] = useState<RewriteAsk | null>(null);
  const save = useSaveDocuments(applicationId);
  const keep = useKeepFlag(applicationId);
  const actions: FlagActions = {
    busy: keep.isPending,
    keep: (flag) => {
      keep.mutate(
        { document: flag.document, location: flag.location, text: flag.text },
        {
          onSuccess: () => toast.success("Kept as written"),
          onError: (error) => toast.error(errorText(error, "Couldn't keep it")),
        },
      );
    },
    soften: (flag) => {
      const section = sectionFor(flag);
      if (section) setAsk({ section, instruction: softenInstruction(flag), at: Date.now() });
    },
    drop: (flag) => {
      const next = dropLine(cv, letter, flag);
      setCv(next.cv);
      setLetter(next.letter);
      setResets((n) => n + 1);
      toast("Line removed. Save to update the files.");
    },
  };
  const version = `${bundle.updated_at}-${String(resets)}`;

  const dirty =
    JSON.stringify(cv) !== JSON.stringify(bundle.cv) ||
    JSON.stringify(letter) !== JSON.stringify(bundle.cover_letter);
  const files = doc === "cv" ? bundle.files.cv : bundle.files.cover_letter;
  const label = doc === "cv" ? "CV" : "Cover letter";

  return (
    <FlagActionsContext.Provider value={actions}>
      <RewriteAskContext.Provider value={ask}>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Document">
              {(["cv", "cover_letter"] as const).map((d) => (
                <Button
                  key={d}
                  size="sm"
                  variant={doc === d ? "default" : "outline"}
                  aria-pressed={doc === d}
                  onClick={() => {
                    onDocChange(d);
                  }}
                >
                  {d === "cv" ? "CV" : "Cover letter"}
                </Button>
              ))}
              <span className="ml-auto flex gap-2">
                {dirty && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setCv(bundle.cv);
                      setLetter(bundle.cover_letter);
                      setResets((n) => n + 1);
                    }}
                  >
                    <Undo2Icon /> Discard
                  </Button>
                )}
                <Button
                  size="sm"
                  disabled={!dirty || save.isPending}
                  onClick={() => {
                    save.mutate(
                      { cv, cover_letter: letter },
                      {
                        onSuccess: (detail) => {
                          const left = detail.documents?.flags.length ?? 0;
                          toast.success(
                            left ? `Saved. ${String(left)} line(s) still need a look.` : "Saved",
                          );
                        },
                        onError: (error) => toast.error(errorText(error, "Couldn't save")),
                      },
                    );
                  }}
                >
                  <SaveIcon /> {save.isPending ? "Saving…" : "Save and update files"}
                </Button>
              </span>
            </div>
            {doc === "cv" ? (
              <CvEditor
                version={version}
                cv={cv}
                flags={bundle.flags}
                applicationId={applicationId}
                onChange={setCv}
                busy={dirty}
              />
            ) : (
              <LetterEditor
                version={version}
                letter={letter}
                flags={bundle.flags}
                applicationId={applicationId}
                onChange={setLetter}
                busy={dirty}
              />
            )}
            {dirty && (
              <p className="text-xs text-muted-foreground">
                Save your edits before rewriting a part.
              </p>
            )}
          </div>
          <div className="space-y-2 lg:sticky lg:top-4 lg:self-start">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="mr-auto text-sm font-medium">{label} preview</h3>
              {(["pdf", "docx"] as const).map((fmt) =>
                files[fmt] ? (
                  <Button key={fmt} size="sm" variant="outline" asChild>
                    <a href={applicationFileUrl(applicationId, doc, fmt)} download>
                      <DownloadIcon /> {fmt === "pdf" ? "PDF" : "Word"}
                    </a>
                  </Button>
                ) : null,
              )}
            </div>
            {files.pdf ? (
              <iframe
                key={`${doc}-${bundle.updated_at}`}
                title={`${label} PDF`}
                src={applicationFileUrl(applicationId, doc, "pdf", bundle.updated_at)}
                className="h-[75dvh] w-full rounded-md border bg-white"
              />
            ) : (
              <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                PDF isn't available (Chromium isn't installed); the Word file is ready. Run{" "}
                <code>offerbound doctor</code> for the fix.
              </p>
            )}
          </div>
        </div>
      </RewriteAskContext.Provider>
    </FlagActionsContext.Provider>
  );
}
