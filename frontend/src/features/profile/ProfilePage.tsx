import { ArrowRightIcon, LinkIcon, MailIcon, MapPinIcon, UserRoundIcon } from "lucide-react";
import { Link } from "react-router";

import {
  useInterview,
  useMemory,
  useProfileOverview,
  useProposals,
  type Preferences,
  type Profile,
  type ProfileOverview,
} from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { DocumentSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
import { MarkdownLite } from "@/components/MarkdownLite";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ProposalChip } from "@/features/memory/ProposalChip";

import { MemoryFileEditor } from "./MemoryFileEditor";
import { isBlankMemory } from "./memoryText";

const REMOTE_LABELS: Record<string, string> = {
  remote: "Remote only",
  hybrid: "Hybrid",
  onsite: "On-site",
  any: "Open to any",
};

function dateRange(start?: string | null, end?: string | null, current?: boolean): string | null {
  if (!start && !end) return null;
  return `${start ?? "?"} – ${current ? "present" : (end ?? "?")}`;
}

function ProfileView({ profile }: { profile: Profile }) {
  const contact = profile.contact;
  const details = [
    contact.email && { icon: MailIcon, text: contact.email },
    contact.location && { icon: MapPinIcon, text: contact.location },
    ...contact.links.map((link) => ({ icon: LinkIcon, text: link })),
  ].filter(Boolean) as { icon: typeof MailIcon; text: string }[];

  return (
    <div className="space-y-6 text-sm">
      <div>
        <p className="text-lg font-semibold">{contact.name ?? "Your name"}</p>
        {profile.headline && <p className="text-muted-foreground">{profile.headline}</p>}
        {details.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
            {details.map(({ icon: Icon, text }) => (
              <li key={text} className="inline-flex items-center gap-1.5">
                <Icon className="size-3.5" aria-hidden />
                {text}
              </li>
            ))}
          </ul>
        )}
        {profile.summary && (
          <p className="mt-3 leading-relaxed whitespace-pre-line">{profile.summary}</p>
        )}
      </div>

      {profile.experience.length > 0 && (
        <section aria-labelledby="experience-heading" className="space-y-3">
          <h3 id="experience-heading" className="font-semibold">
            Experience
          </h3>
          {profile.experience.map((exp, index) => (
            <article key={`${exp.title}-${String(index)}`} className="border-l-2 pl-3">
              <p className="font-medium">
                {exp.title}
                {exp.company && (
                  <span className="font-normal text-muted-foreground"> · {exp.company}</span>
                )}
              </p>
              <p className="text-xs text-muted-foreground">
                {[dateRange(exp.start, exp.end, exp.current), exp.location]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              {exp.highlights.length > 0 && (
                <ul className="mt-1.5 list-disc space-y-1 pl-5">
                  {exp.highlights.map((h) => (
                    <li key={h}>{h}</li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </section>
      )}

      {profile.education.length > 0 && (
        <section aria-labelledby="education-heading" className="space-y-2">
          <h3 id="education-heading" className="font-semibold">
            Education
          </h3>
          {profile.education.map((edu, index) => (
            <p key={`${edu.institution}-${String(index)}`}>
              {[edu.degree, edu.field].filter(Boolean).join(", ")}
              {edu.degree || edu.field ? " · " : ""}
              {edu.institution}
              {dateRange(edu.start, edu.end) && (
                <span className="text-muted-foreground"> · {dateRange(edu.start, edu.end)}</span>
              )}
            </p>
          ))}
        </section>
      )}

      {profile.skills.length > 0 && (
        <section aria-labelledby="skills-heading" className="space-y-2">
          <h3 id="skills-heading" className="font-semibold">
            Skills
          </h3>
          <ul className="flex flex-wrap gap-1.5">
            {profile.skills.map((skill) => (
              <li key={skill}>
                <Badge variant="secondary">{skill}</Badge>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function PreferencesView({ prefs }: { prefs: Preferences }) {
  const salary = prefs.salary_floor;
  const rows: [string, string | null][] = [
    ["Target titles", prefs.target_titles.join(", ") || null],
    ["Level", prefs.seniority ?? null],
    ["Work style", prefs.remote ? (REMOTE_LABELS[prefs.remote] ?? prefs.remote) : null],
    ["Locations", prefs.locations.join(", ") || null],
    ["Country", prefs.country ?? null],
    [
      "Salary floor",
      salary
        ? `${new Intl.NumberFormat(undefined, { style: "currency", currency: salary.currency, maximumFractionDigits: 0 }).format(salary.amount)} per ${salary.period}`
        : null,
    ],
    ["Work authorization", prefs.work_authorization ?? null],
    ["Deal-breakers", prefs.deal_breakers.join(", ") || null],
    ["Work that energizes you", prefs.energizing.join(", ") || null],
    ["Work that drains you", prefs.draining.join(", ") || null],
  ];
  return (
    <div className="space-y-4">
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className={value ? "" : "text-muted-foreground italic"}>{value ?? "Not set"}</dd>
          </div>
        ))}
      </dl>
      <div className="space-y-1.5 text-sm">
        <h3 className="font-medium">Application answers</h3>
        <p className="text-muted-foreground">
          Reused when Claude fills in application forms. Add them under "Application answers" when
          you edit this file, one per line, like "Will you need visa sponsorship? No".
        </p>
        {prefs.answers.length > 0 ? (
          <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-[minmax(10rem,22rem)_1fr]">
            {prefs.answers.map((a) => (
              <div key={a.question} className="contents">
                <dt className="text-muted-foreground">{a.question}</dt>
                <dd>{a.answer}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-muted-foreground italic">None saved yet.</p>
        )}
      </div>
    </div>
  );
}

function CompletenessCard({
  overview,
  setupDone,
}: {
  overview: ProfileOverview;
  setupDone: boolean;
}) {
  const { score, missing } = overview.completeness;
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex-1 space-y-2">
          <div className="flex items-baseline justify-between">
            <p className="font-medium">Profile {score}% complete</p>
          </div>
          <Progress value={score} aria-label="Profile completeness" className="h-2" />
          {missing.length > 0 && (
            <p className="text-xs text-muted-foreground">Missing: {missing.join(", ")}</p>
          )}
        </div>
        {!setupDone && (
          <Button asChild>
            <Link to="/onboarding?step=interview">
              Continue setup <ArrowRightIcon />
            </Link>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export default function ProfilePage() {
  const overview = useProfileOverview();
  const memory = useMemory();
  const proposals = useProposals();
  const interview = useInterview();

  if (overview.isPending || memory.isPending) return <DocumentSkeleton />;
  if (overview.isError || memory.isError) {
    return (
      <div className="px-5 py-7 md:px-8" role="alert">
        Couldn't load your profile.
      </div>
    );
  }

  const pending = proposals.data ?? [];
  const blank = isBlankMemory(memory.data.profile) && isBlankMemory(memory.data.preferences);
  const targets = overview.data.search_targets.filter((t) => t.active);

  return (
    <>
      <PageHeader
        title="Profile"
        description="Your source of truth. Generated documents only use facts written here."
        actions={
          !blank && (
            <Button asChild variant="outline">
              <Link to="/onboarding?step=resume">Import a resume</Link>
            </Button>
          )
        }
      />
      <div className="max-w-3xl space-y-6 px-5 pb-8 md:px-8">
        {pending.length > 0 && (
          <section aria-labelledby="pending-heading" className="space-y-2">
            <h2 id="pending-heading" className="text-sm font-semibold">
              Suggested updates ({pending.length})
            </h2>
            {pending.map((proposal) => (
              <ProposalChip key={proposal.id} proposal={proposal} />
            ))}
          </section>
        )}
        {blank ? (
          <EmptyState
            icon={UserRoundIcon}
            title="Your profile is empty"
            description="Import a resume or LinkedIn export, or answer a few questions. Nothing is saved without your OK."
            steps={[
              {
                title: "Import a resume",
                description: "PDF, Word, text, or your LinkedIn data export.",
                action: { label: "Import", to: "/onboarding?step=resume" },
              },
              {
                title: "Or answer questions",
                description: "About 10 minutes, one question at a time. No resume needed.",
                action: { label: "Start questions", to: "/onboarding?step=interview" },
              },
              {
                title: "Find jobs",
                description: "Your preferences become search targets for job sources.",
                action: { label: "Choose sources", to: "/sources" },
              },
            ]}
          />
        ) : (
          <>
            <CompletenessCard
              overview={overview.data}
              setupDone={interview.data?.complete ?? false}
            />
            <MemoryFileEditor title="Profile" target="profile" markdown={memory.data.profile}>
              <ProfileView profile={overview.data.profile} />
            </MemoryFileEditor>
            <MemoryFileEditor
              title="Preferences"
              target="preferences"
              markdown={memory.data.preferences}
            >
              <PreferencesView prefs={overview.data.preferences} />
            </MemoryFileEditor>
            {targets.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Search targets</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-1 text-sm">
                    {targets.map((t) => (
                      <li key={t.id}>
                        <span className="font-medium">{t.title}</span>
                        <span className="text-muted-foreground">
                          {" · "}
                          {[REMOTE_LABELS[t.remote_policy], ...t.locations, t.country]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
            <MemoryFileEditor title="Facts" target="facts" markdown={memory.data.facts}>
              <MarkdownLite markdown={memory.data.facts} />
            </MemoryFileEditor>
          </>
        )}
      </div>
    </>
  );
}
