import { useId } from "react";

import { usePortals, type LLMStatus } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { sourceSummary } from "./settingsText";
import { PRODUCT_NAME } from "@/lib/brand";

function Row({
  name,
  status,
  children,
}: {
  name: string;
  status?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1 border-t py-3 first:border-t-0 first:pt-0 sm:grid-cols-[10rem_1fr] sm:gap-4">
      <dt className="flex items-start gap-2 text-sm font-medium">
        {name}
        {status && <Badge variant="secondary">{status}</Badge>}
      </dt>
      <dd className="text-sm text-muted-foreground">{children}</dd>
    </div>
  );
}

/** Every place the app sends data, from what is actually turned on (spec: Security). */
export function DestinationsCard({ status }: { status: LLMStatus }) {
  const portals = usePortals();
  const titleId = useId();
  const sources = sourceSummary(portals.data ?? []);

  return (
    <Card role="region" aria-labelledby={titleId}>
      <CardHeader>
        <CardTitle id={titleId}>Where your data goes</CardTitle>
        <CardDescription>
          {PRODUCT_NAME} only talks to these. No analytics, no tracking, no account.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl>
          <Row name="Anthropic" status={status.configured ? "In use" : "Not in use"}>
            When Claude ranks jobs, writes or reviews documents, or chats: the parts of your profile
            and memory the task needs, plus the job postings involved. Billed to your own API key.
          </Row>
          <Row name="Job sources">
            Your search titles and locations, to fetch public job listings.{" "}
            {portals.isPending
              ? "Loading your sources…"
              : sources
                ? `Turned on: ${sources}.`
                : "None are turned on."}
          </Row>
          <Row name="Employer sites">
            Only the application pages you open with autofill, and job pages you ask Add a job to
            read (a plain page request; nothing of yours is sent). Autofill fills in fields and
            stops; it never submits.
          </Row>
          <Row name="GitHub">
            Only when you run <code className="font-mono text-xs">rolehawk update</code>, to
            download the new version.
          </Row>
        </dl>
      </CardContent>
    </Card>
  );
}
