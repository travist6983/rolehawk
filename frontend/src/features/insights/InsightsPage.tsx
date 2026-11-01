import { ChartColumnIcon, DownloadIcon, FileCodeIcon } from "lucide-react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { reportUrl, useCreateReport, useInsights, type Insights } from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ChartSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { usd } from "@/lib/format";

import { CalibrationCard } from "./CalibrationCard";
import { ChartCard, Columns, HorizontalBars } from "./Charts";
import { compactNumber, pct, weekLabel } from "./insightsText";

function StatTile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {detail && <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}

function SpendTile({ spend }: { spend: Insights["spend"] }) {
  const cap = spend.cap_usd;
  const share = cap ? Math.min(spend.month_to_date_usd / cap, 1) : null;
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-sm text-muted-foreground">AI spend this month</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{usd(spend.month_to_date_usd)}</p>
      {share !== null && cap !== null ? (
        <div className="mt-2 space-y-1">
          <Progress value={Math.round(share * 100)} aria-label="Share of monthly cap used" />
          <p className="text-xs text-muted-foreground">of your {usd(cap)} cap</p>
        </div>
      ) : (
        <p className="mt-0.5 text-xs text-muted-foreground">No monthly cap set</p>
      )}
    </div>
  );
}

function ReportButton() {
  const report = useCreateReport();
  return (
    <div className="flex flex-wrap items-center gap-2">
      {report.data && (
        <Button variant="outline" asChild>
          <a href={reportUrl(report.data.filename)} download>
            <DownloadIcon /> Download report
          </a>
        </Button>
      )}
      <Button
        disabled={report.isPending}
        onClick={() => {
          report.mutate(undefined, {
            onSuccess: (file) => toast.success(`Report saved to ${file.path}`),
            onError: (error) => toast.error(errorText(error, "Couldn't create the report")),
          });
        }}
      >
        <FileCodeIcon /> {report.isPending ? "Creating…" : "Export HTML report"}
      </Button>
    </div>
  );
}

export default function InsightsPage() {
  const insights = useInsights();
  const header = (
    <PageHeader
      title="Insights"
      description="Your funnel, response rates, activity, and spend."
      actions={<ReportButton />}
    />
  );
  if (insights.isPending) return <ChartSkeleton />;
  if (insights.isError) {
    return (
      <>
        {header}
        <EmptyState
          icon={ChartColumnIcon}
          title="Couldn't load insights"
          description={errorText(insights.error, "The Offerbound backend didn't answer.")}
        />
      </>
    );
  }
  const data = insights.data;
  const t = data.totals;
  if (t.applications === 0) {
    return (
      <>
        {header}
        <EmptyState
          icon={ChartColumnIcon}
          title="Nothing to chart yet"
          description="Your funnel and response rates appear once you save or apply to jobs."
          steps={[
            {
              title: "Find jobs",
              description: "Run a search from Sources.",
              action: { label: "Sources", to: "/sources" },
            },
            {
              title: "Pick the best",
              description: "Rank and save jobs in Discover.",
              action: { label: "Discover", to: "/discover" },
            },
            {
              title: "Apply",
              description: "Tailored documents, fact-checked.",
              action: { label: "Pipeline", to: "/" },
            },
          ]}
        />
        <div className="mx-auto max-w-sm px-6 pb-6">
          <SpendTile spend={data.spend} />
        </div>
      </>
    );
  }

  const funnel = data.funnel.map((step) => ({
    label: step.label,
    value: step.count,
    text:
      step.rate_from_previous === null
        ? String(step.count)
        : `${String(step.count)} (${pct(step.rate_from_previous)})`,
  }));
  const sources = data.by_source.map((s) => ({
    label: s.source,
    value: s.rate,
    text: `${pct(s.rate)} of ${String(s.applied)}`,
  }));
  const weekly = data.weekly.map((w) => ({
    label: weekLabel(w.week_start),
    value: w.applied,
    text: `${String(w.applied)} sent, ${compactNumber(w.jobs_found)} jobs found`,
  }));
  const spend = data.spend.by_command.map((line) => ({
    label: line.command,
    value: line.cost_usd,
    text: `${usd(line.cost_usd)} (${String(line.calls)} calls)`,
  }));

  return (
    <>
      {header}
      <div className="space-y-6 p-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <StatTile
            label="Applications"
            value={String(t.applications)}
            detail={`${String(t.active)} active`}
          />
          <StatTile label="Applied" value={String(t.applied)} />
          <StatTile
            label="Response rate"
            value={pct(t.response_rate)}
            detail={`${String(t.responses)} responses`}
          />
          <StatTile
            label="Interviews"
            value={String(t.interviews)}
            detail={`${String(t.offers)} offer${t.offers === 1 ? "" : "s"}`}
          />
          <SpendTile spend={data.spend} />
        </div>
        <CalibrationCard />
        <div className="grid gap-6 xl:grid-cols-2">
          <ChartCard
            title="Pipeline funnel"
            description="Applications that reached each stage, and the share that moved on from the stage before."
            table={{
              headers: ["Stage", "Reached", "From previous"],
              rows: data.funnel.map((s) => [s.label, s.count, pct(s.rate_from_previous)]),
            }}
          >
            <HorizontalBars data={funnel} label="Pipeline funnel" />
          </ChartCard>
          <ChartCard
            title="Response rate by source"
            description="A response is a screen, an interview, an offer, or a rejection."
            table={{
              headers: ["Source", "Applied", "Responses", "Rate"],
              rows: data.by_source.map((s) => [s.source, s.applied, s.responses, pct(s.rate)]),
            }}
          >
            {sources.length > 0 ? (
              <HorizontalBars data={sources} label="Response rate by source" max={1} />
            ) : (
              <p className="text-sm text-muted-foreground">No applications sent yet.</p>
            )}
          </ChartCard>
          <ChartCard
            title="Applications sent per week"
            description="The last 12 weeks, weeks starting Monday."
            table={{
              headers: ["Week of", "Applied", "Jobs found"],
              rows: data.weekly.map((w) => [w.week_start, w.applied, w.jobs_found]),
            }}
          >
            <Columns data={weekly} label="Applications sent per week" />
          </ChartCard>
          <ChartCard
            title="AI spend by command this month"
            table={{
              headers: ["Command", "Cost", "Calls"],
              rows: data.spend.by_command.map((l) => [l.command, usd(l.cost_usd), l.calls]),
            }}
          >
            {spend.length > 0 ? (
              <HorizontalBars data={spend} label="AI spend by command this month" />
            ) : (
              <p className="text-sm text-muted-foreground">No AI calls this month.</p>
            )}
          </ChartCard>
        </div>
      </div>
    </>
  );
}
