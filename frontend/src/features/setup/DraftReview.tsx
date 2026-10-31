import { ShieldCheckIcon, Trash2Icon, XIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useApplyDraft, useDiscardDraft, type Draft } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { summarizeApply } from "./summary";

function dates(start?: string | null, end?: string | null, current?: boolean): string {
  if (!start && !end) return "";
  return `${start ?? "?"} - ${current ? "present" : (end ?? "?")}`;
}

/** Review what was read from the documents before anything is saved. */
export function DraftReview({ draft, onApplied }: { draft: Draft; onApplied: () => void }) {
  const [profile, setProfile] = useState(draft.profile);
  const apply = useApplyDraft();
  const discard = useDiscardDraft();
  const ids = {
    name: useId(),
    email: useId(),
    location: useId(),
    headline: useId(),
    summary: useId(),
  };
  const contact = profile.contact;

  const setContact = (field: "name" | "email" | "location", value: string) => {
    setProfile({ ...profile, contact: { ...contact, [field]: value || null } });
  };

  const experience = profile.experience;
  const education = profile.education;
  const skills = profile.skills;

  return (
    <div className="space-y-5">
      <div className="flex gap-3 rounded-lg border border-primary/30 bg-primary/5 p-4 text-sm">
        <ShieldCheckIcon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <p>
          <span className="font-medium">Check every line.</span> Generated CVs and cover letters
          only use what you save here. Remove anything that's wrong; you can add details next.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">About you</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          {(
            [
              ["name", "Name"],
              ["email", "Email"],
              ["location", "Location"],
            ] as const
          ).map(([field, label]) => (
            <div key={field} className="space-y-1.5">
              <Label htmlFor={ids[field]}>{label}</Label>
              <Input
                id={ids[field]}
                value={contact[field] ?? ""}
                onChange={(e) => {
                  setContact(field, e.target.value);
                }}
              />
            </div>
          ))}
          <div className="space-y-1.5 sm:col-span-3">
            <Label htmlFor={ids.headline}>Headline</Label>
            <Input
              id={ids.headline}
              value={profile.headline ?? ""}
              onChange={(e) => {
                setProfile({ ...profile, headline: e.target.value || null });
              }}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-3">
            <Label htmlFor={ids.summary}>Summary</Label>
            <Textarea
              id={ids.summary}
              value={profile.summary ?? ""}
              onChange={(e) => {
                setProfile({ ...profile, summary: e.target.value || null });
              }}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Experience ({experience.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {experience.length === 0 && (
            <p className="text-sm text-muted-foreground">No roles found. You can add them next.</p>
          )}
          {experience.map((exp, index) => (
            <article key={`${exp.title}-${String(index)}`} className="rounded-lg border p-3">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h3 className="font-medium">
                    {exp.title}
                    {exp.company ? ` · ${exp.company}` : ""}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {[dates(exp.start, exp.end, exp.current), exp.location]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  aria-label={`Remove ${exp.title}${exp.company ? ` at ${exp.company}` : ""}`}
                  onClick={() => {
                    setProfile({
                      ...profile,
                      experience: experience.filter((_, i) => i !== index),
                    });
                  }}
                >
                  <Trash2Icon />
                </Button>
              </div>
              {exp.highlights.length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                  {exp.highlights.map((h) => (
                    <li key={h}>{h}</li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </CardContent>
      </Card>

      {education.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Education</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {education.map((edu, index) => (
              <div
                key={`${edu.institution}-${String(index)}`}
                className="flex items-center gap-2 text-sm"
              >
                <span className="flex-1">
                  {[edu.degree, edu.field].filter(Boolean).join(", ")}
                  {edu.degree || edu.field ? " · " : ""}
                  {edu.institution}
                </span>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  aria-label={`Remove ${edu.institution}`}
                  onClick={() => {
                    setProfile({ ...profile, education: education.filter((_, i) => i !== index) });
                  }}
                >
                  <Trash2Icon />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Skills ({skills.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-wrap gap-2">
            {skills.map((skill) => (
              <li
                key={skill}
                className="inline-flex items-center gap-1 rounded-full border bg-card py-1 pr-1 pl-3 text-sm"
              >
                {skill}
                <button
                  type="button"
                  aria-label={`Remove skill ${skill}`}
                  className="rounded-full p-0.5 hover:bg-accent"
                  onClick={() => {
                    setProfile({ ...profile, skills: skills.filter((s) => s !== skill) });
                  }}
                >
                  <XIcon className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button
          disabled={apply.isPending}
          onClick={() => {
            apply.mutate(
              { profile, preferences: draft.preferences },
              {
                onSuccess: (result) => {
                  toast.success(summarizeApply(result));
                  onApplied();
                },
                onError: (error) => toast.error(errorText(error, "Couldn't save your profile")),
              },
            );
          }}
        >
          {apply.isPending ? "Saving…" : "Save to profile"}
        </Button>
        <Button
          variant="ghost"
          disabled={discard.isPending}
          onClick={() => {
            discard.mutate();
          }}
        >
          Discard
        </Button>
      </div>
    </div>
  );
}
