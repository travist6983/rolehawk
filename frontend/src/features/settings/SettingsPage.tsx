import { CheckCircle2Icon, ExternalLinkIcon, KeyRoundIcon, TerminalIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import {
  useClearApiKey,
  useLLMStatus,
  useModels,
  useSessionInfo,
  useSetApiKey,
  useUpdateLLMSettings,
  type LLMStatus,
} from "@/api/queries";
import { FormSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
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
import { Switch } from "@/components/ui/switch";

const CONSOLE_KEYS_URL = "https://console.anthropic.com/settings/keys";
const TASK_LABELS: Record<string, string> = {
  rank: "Ranking jobs",
  extract: "Reading and remembering",
  write: "Writing CVs and letters",
  review: "Truthfulness review",
  chat: "Chat",
};

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function ConnectionCard({ status }: { status: LLMStatus }) {
  const [key, setKey] = useState("");
  const setApiKey = useSetApiKey();
  const clearApiKey = useClearApiKey();
  const inputId = useId();
  const fromKeychain = status.key_source === "keychain";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Claude connection
          {status.configured ? (
            <Badge variant="secondary" className="gap-1">
              <CheckCircle2Icon className="size-3.5 text-score-high" aria-hidden /> Connected
            </Badge>
          ) : (
            <Badge variant="outline">Not connected</Badge>
          )}
        </CardTitle>
        <CardDescription>
          Offerbound uses your own Anthropic API key. It's stored in your operating system's
          keychain, never in a file.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="flex flex-col gap-2 sm:flex-row sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            setApiKey.mutate(key, {
              onSuccess: () => {
                setKey("");
                toast.success("API key saved and verified");
              },
              onError: (error) => toast.error(errorText(error, "Couldn't save the key")),
            });
          }}
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor={inputId}>
              {status.configured ? "Replace API key" : "Anthropic API key"}
            </Label>
            <Input
              id={inputId}
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="sk-ant-..."
              value={key}
              onChange={(event) => {
                setKey(event.target.value);
              }}
            />
          </div>
          <Button type="submit" disabled={key.trim().length < 10 || setApiKey.isPending}>
            <KeyRoundIcon /> {setApiKey.isPending ? "Checking…" : "Save and test"}
          </Button>
        </form>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <a
            href={CONSOLE_KEYS_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
          >
            Get a key from the Anthropic Console{" "}
            <ExternalLinkIcon className="size-3.5" aria-hidden />
          </a>
          {fromKeychain && (
            <Button
              variant="ghost"
              size="sm"
              disabled={clearApiKey.isPending}
              onClick={() => {
                clearApiKey.mutate(undefined, {
                  onSuccess: () => toast("API key removed"),
                  onError: (error) => toast.error(errorText(error, "Couldn't remove the key")),
                });
              }}
            >
              Remove key
            </Button>
          )}
          {status.key_source === "env" && (
            <span className="text-muted-foreground">
              Using ANTHROPIC_API_KEY from the environment.
            </span>
          )}
        </div>
        <div className="flex gap-3 rounded-lg bg-muted/50 p-3 text-sm">
          <TerminalIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <p>
            <span className="font-medium">Using Claude Code?</span>{" "}
            <span className="text-muted-foreground">
              Run any command from your terminal with the Offerbound skills; Claude Code does the
              work in your own session, so no key is needed here.
            </span>
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

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
