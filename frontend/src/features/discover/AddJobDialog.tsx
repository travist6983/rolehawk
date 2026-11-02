import { LinkIcon } from "lucide-react";
import { useId, useState } from "react";

import { errorText } from "@/api/errors";
import { useAddJob, useReadJobLink, type AddedJob, type LinkDraft } from "@/api/queries";
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
import { Textarea } from "@/components/ui/textarea";

interface Fields {
  url: string;
  title: string;
  company: string;
  location: string;
  description: string;
}

const EMPTY: Fields = { url: "", title: "", company: "", location: "", description: "" };

function filled(fields: Fields, draft: LinkDraft): Fields {
  return {
    url: fields.url,
    title: draft.title ?? fields.title,
    company: draft.company ?? fields.company,
    location: draft.location ?? fields.location,
    description: draft.description || fields.description,
  };
}

export function AddJobDialog({
  open,
  onOpenChange,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: (added: AddedJob) => void;
}) {
  const [fields, setFields] = useState<Fields>(EMPTY);
  const [draft, setDraft] = useState<LinkDraft | null>(null);
  const read = useReadJobLink();
  const add = useAddJob();
  const ids = {
    url: useId(),
    title: useId(),
    company: useId(),
    location: useId(),
    description: useId(),
  };
  const busy = read.isPending || add.isPending;

  const close = () => {
    setFields(EMPTY);
    setDraft(null);
    read.reset();
    add.reset();
    onOpenChange(false);
  };
  const set = (key: keyof Fields) => (event: { target: { value: string } }) => {
    setFields((current) => ({ ...current, [key]: event.target.value }));
  };
  const readLink = () => {
    add.reset();
    read.mutate(fields.url.trim(), {
      onSuccess: (result) => {
        setDraft(result);
        setFields((current) => filled(current, result));
      },
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a job</DialogTitle>
          <DialogDescription>
            Found one on LinkedIn, Indeed, or a company site? Paste the link and the posting's text.
            It's ranked and tracked like any other job.
          </DialogDescription>
        </DialogHeader>

        <form
          id="add-job"
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            add.mutate(
              {
                url: fields.url.trim(),
                title: fields.title.trim(),
                company: fields.company.trim(),
                location: fields.location.trim() || null,
                description: fields.description.trim(),
                // Dates from the link's page, when the link wasn't changed after reading it.
                ...(draft && draft.url === fields.url.trim()
                  ? { posted_at: draft.posted_at, closes_at: draft.closes_at }
                  : {}),
              },
              {
                onSuccess: (added) => {
                  close();
                  onAdded(added);
                },
              },
            );
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor={ids.url}>Link to the posting</Label>
            <div className="flex flex-wrap gap-2">
              <Input
                id={ids.url}
                type="url"
                required
                className="min-w-60 flex-1"
                placeholder="https://www.linkedin.com/jobs/view/…"
                value={fields.url}
                onChange={set("url")}
              />
              <Button
                type="button"
                variant="outline"
                disabled={busy || !fields.url.trim()}
                onClick={readLink}
              >
                <LinkIcon aria-hidden />
                {read.isPending ? "Reading…" : "Fill in from link"}
              </Button>
            </div>
            <div aria-live="polite" className="empty:hidden">
              {read.error && (
                <p role="alert" className="text-sm text-muted-foreground">
                  {errorText(
                    read.error,
                    "Couldn't read that link. Paste the posting's text below.",
                  )}
                </p>
              )}
              {draft?.found === "page" && (
                <p className="text-sm text-muted-foreground">
                  That page has no structured job data, so this is its text. Check the title and
                  company.
                </p>
              )}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={ids.title}>Job title</Label>
              <Input id={ids.title} required value={fields.title} onChange={set("title")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={ids.company}>Company</Label>
              <Input id={ids.company} required value={fields.company} onChange={set("company")} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={ids.location}>Location</Label>
            <Input
              id={ids.location}
              placeholder="City, or Remote"
              value={fields.location}
              onChange={set("location")}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={ids.description}>Posting text</Label>
            <Textarea
              id={ids.description}
              rows={8}
              placeholder="Paste the job description. Ranking and /apply work from it."
              value={fields.description}
              onChange={set("description")}
            />
          </div>
          {add.error && (
            <p role="alert" className="text-sm text-destructive">
              {errorText(add.error, "Couldn't add the job. Try again.")}
            </p>
          )}
        </form>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" form="add-job" disabled={busy}>
            {add.isPending ? "Adding…" : "Add job"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
