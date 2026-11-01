import { CheckIcon, RadioTowerIcon, SearchIcon } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useDocuments,
  useInterview,
  useLLMStatus,
  usePortals,
  useProfileOverview,
  useStartScrape,
} from "@/api/queries";
import { FormSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { ConnectClaudeStep } from "./ConnectClaudeStep";
import { InterviewStep } from "./InterviewStep";
import { ResumeStep } from "./ResumeStep";

const STEPS = [
  { id: "connect", label: "Connect Claude" },
  { id: "resume", label: "Resume" },
  { id: "interview", label: "Questions" },
  { id: "sources", label: "Job sources" },
] as const;

type StepId = (typeof STEPS)[number]["id"];

const WORK_STYLE: Record<string, string> = {
  remote: "Remote only",
  hybrid: "Hybrid",
  onsite: "On-site",
  any: "Open to any",
};

function isStep(value: string | null): value is StepId {
  return STEPS.some((s) => s.id === value);
}

function Stepper({ current, done }: { current: StepId; done: ReadonlySet<StepId> }) {
  const index = STEPS.findIndex((s) => s.id === current);
  return (
    <ol className="flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Setup steps">
      {STEPS.map((step, i) => {
        const state =
          i === index ? "current" : done.has(step.id) ? "done" : i < index ? "skipped" : "todo";
        return (
          <li
            key={step.id}
            aria-current={state === "current" ? "step" : undefined}
            className={cn(
              "flex items-center gap-2",
              state === "current" ? "font-medium text-foreground" : "text-muted-foreground",
            )}
          >
            <span
              className={cn(
                "grid size-6 place-items-center rounded-full border text-xs",
                state === "done" && "border-primary bg-primary text-primary-foreground",
                state === "current" && "border-primary text-primary-text",
                state === "skipped" && "border-dashed",
              )}
            >
              {state === "done" ? (
                <CheckIcon className="size-3.5" aria-hidden />
              ) : state === "skipped" ? (
                "–"
              ) : (
                i + 1
              )}
            </span>
            {step.label}
            {(state === "done" || state === "skipped") && (
              <span className="sr-only">({state})</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function SourcesStep({ onFinish }: { onFinish: (searching: boolean) => void }) {
  const overview = useProfileOverview();
  const portals = usePortals();
  const start = useStartScrape();
  const targets = (overview.data?.search_targets ?? []).filter((t) => t.active);
  const ready = (portals.data ?? []).filter((p) => p.enabled && p.ready);
  const companies = (portals.data ?? []).reduce((sum, p) => sum + (p.companies ?? 0), 0);
  const canSearch = targets.length > 0 && ready.length > 0;
  return (
    <div className="space-y-5">
      <div className="flex gap-3 rounded-lg border bg-card p-4">
        <RadioTowerIcon className="mt-0.5 size-5 text-primary" aria-hidden />
        <div className="text-sm">
          <p className="font-medium">
            {portals.isPending
              ? "Checking job sources…"
              : `${String(ready.length)} job sources are ready`}
          </p>
          <p className="text-muted-foreground">
            Public job boards for a starter watchlist of {companies.toLocaleString("en")} companies,
            plus remote job feeds. Nothing to sign up for. Add companies any time in{" "}
            <Link to="/sources" className="text-primary-text underline-offset-4 hover:underline">
              Sources
            </Link>
            .
          </p>
        </div>
      </div>
      {targets.length > 0 ? (
        <ul className="space-y-2" aria-label="Search targets">
          {targets.map((t) => (
            <li key={t.id} className="rounded-lg border px-3 py-2 text-sm">
              <span className="font-medium">{t.title}</span>
              <span className="text-muted-foreground">
                {" · "}
                {[WORK_STYLE[t.remote_policy], ...t.locations, t.country]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          No target job titles yet, so there's nothing to search for. Add them in Profile.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {canSearch && (
          <Button
            disabled={start.isPending}
            onClick={() => {
              start.mutate(undefined, {
                onSuccess: () => {
                  onFinish(true);
                },
                onError: (error) => toast.error(errorText(error, "Couldn't start the search")),
              });
            }}
          >
            <SearchIcon /> Search now
          </Button>
        )}
        <Button
          variant={canSearch ? "outline" : "default"}
          onClick={() => {
            onFinish(false);
          }}
        >
          Finish setup
        </Button>
      </div>
    </div>
  );
}

export default function OnboardingPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const status = useLLMStatus();
  const documents = useDocuments();
  const interview = useInterview();
  const requested = params.get("step");

  if (status.isPending) return <FormSkeleton label="Loading setup" />;
  const step: StepId = isStep(requested)
    ? requested
    : status.data?.configured
      ? "resume"
      : "connect";
  const go = (next: StepId) => {
    setParams({ step: next });
  };

  return (
    <>
      <PageHeader
        title="Set up your profile"
        description="About 10 minutes. You can stop and come back any time."
      />
      <div className="mx-auto max-w-3xl space-y-8 p-6">
        <Stepper
          current={step}
          done={
            new Set<StepId>([
              ...(status.data?.configured ? (["connect"] as const) : []),
              ...((documents.data?.length ?? 0) > 0 ? (["resume"] as const) : []),
              ...(interview.data?.complete ? (["interview"] as const) : []),
            ])
          }
        />
        {step === "connect" && status.data && (
          <ConnectClaudeStep
            status={status.data}
            onContinue={() => {
              go("resume");
            }}
            onUseClaudeCode={() => {
              go("interview");
            }}
          />
        )}
        {step === "resume" && (
          <ResumeStep
            onNext={() => {
              go("interview");
            }}
          />
        )}
        {step === "interview" && (
          <InterviewStep
            onDone={() => {
              go("sources");
            }}
          />
        )}
        {step === "sources" && (
          <SourcesStep
            onFinish={(searching) => {
              void navigate(searching ? "/sources" : "/profile");
            }}
          />
        )}
      </div>
    </>
  );
}
