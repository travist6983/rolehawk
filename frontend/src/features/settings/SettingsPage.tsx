import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useLLMStatus,
  useModels,
  useSessionInfo,
  useUpdateLLMSettings,
  type LLMStatus,
} from "@/api/queries";
import { FormSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
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
import { Switch } from "@/components/ui/switch";

import { ConnectionCard } from "./ConnectionCard";

const TASK_LABELS: Record<string, string> = {
  rank: "Ranking jobs",
  extract: "Reading and remembering",
  write: "Writing CVs and letters",
  review: "Truthfulness review",
  chat: "Chat",
};

function ModelCard({ status }: { status: LLMStatus }) {
  const models = useModels();
  const update = useUpdateLLMSettings();
  const routingId = useId();
  const modelId = useId();
  const options = models.data ?? [{ id: status.model, display_name: status.model }];

  const save = (body: Parameters<typeof update.mutate>[0]) => {
    update.mutate(body, { onError: (error) => toast.error(errorText(error, "Couldn't save")) });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Model</CardTitle>
        <CardDescription>
          One model for everything, with optional smart routing to save money.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="max-w-sm space-y-1.5">
          <Label htmlFor={modelId}>Model</Label>
          <Select
            value={status.model}
            onValueChange={(model) => {
              save({ model });
            }}
          >
            <SelectTrigger id={modelId} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.map((model) => (
                <SelectItem key={model.id} value={model.id}>
                  {model.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-start gap-3">
          <Switch
            id={routingId}
            checked={status.smart_routing}
            onCheckedChange={(smart_routing) => {
              save({ smart_routing });
            }}
          />
          <div className="space-y-0.5">
            <Label htmlFor={routingId}>Smart routing</Label>
            <p className="text-sm text-muted-foreground">
              Use a small, cheap model for ranking and memory; your chosen model for writing and
              chat.
            </p>
          </div>
        </div>
        <table className="w-full max-w-lg text-sm">
          <caption className="mb-2 text-left text-xs text-muted-foreground">
            Which model does what
          </caption>
          <tbody className="divide-y">
            {status.routes.map((route) => (
              <tr key={route.task}>
                <th scope="row" className="py-1.5 pr-4 text-left font-normal">
                  {TASK_LABELS[route.task] ?? route.task}
                </th>
                <td className="py-1.5 font-mono text-xs">{route.model}</td>
                <td className="py-1.5 text-right text-xs text-muted-foreground">
                  {route.effort ?? ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function SpendCard({ status }: { status: LLMStatus }) {
  const update = useUpdateLLMSettings();
  const [cap, setCap] = useState(status.monthly_cap_usd?.toString() ?? "");
  const capId = useId();
  const spent = status.month_to_date_usd;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Spend</CardTitle>
        <CardDescription>
          Every AI call is logged with its cost. Batch jobs show an estimate first.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm">
          <span className="font-mono text-2xl font-semibold tabular-nums">${spent.toFixed(2)}</span>{" "}
          <span className="text-muted-foreground">this month</span>
          {status.monthly_cap_usd != null && (
            <span className="text-muted-foreground">
              {" "}
              of ${status.monthly_cap_usd.toFixed(2)} cap
            </span>
          )}
        </p>
        <form
          className="flex max-w-sm items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const value = cap.trim() === "" ? null : Number(cap);
            if (value !== null && (!Number.isFinite(value) || value < 0)) {
              toast.error("Enter a positive number, or leave it empty for no cap");
              return;
            }
            update.mutate(
              { monthly_cap_usd: value },
              {
                onSuccess: () =>
                  toast.success(value === null ? "Spend cap removed" : "Spend cap saved"),
                onError: (error) => toast.error(errorText(error, "Couldn't save the cap")),
              },
            );
          }}
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor={capId}>Monthly cap (USD)</Label>
            <Input
              id={capId}
              inputMode="decimal"
              placeholder="No cap"
              value={cap}
              onChange={(event) => {
                setCap(event.target.value);
              }}
            />
          </div>
          <Button type="submit" variant="outline" disabled={update.isPending}>
            Save
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function DataCard() {
  const session = useSessionInfo();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your data</CardTitle>
        <CardDescription>
          Everything stays on this computer in readable files and one database.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm">
          Data folder:{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
            {session.data?.data_root ?? "…"}
          </code>
        </p>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const status = useLLMStatus();
  if (status.isPending) return <FormSkeleton />;
  if (status.isError) {
    return (
      <div className="p-6" role="alert">
        Couldn't load settings: {errorText(status.error, "unknown error")}
      </div>
    );
  }
  return (
    <>
      <PageHeader title="Settings" description="Claude connection, models, spend, and your data." />
      <div className="mx-auto grid max-w-3xl gap-6 p-6">
        <ConnectionCard status={status.data} />
        <ModelCard status={status.data} />
        <SpendCard key={status.data.monthly_cap_usd ?? "none"} status={status.data} />
        <DataCard />
      </div>
    </>
  );
}
