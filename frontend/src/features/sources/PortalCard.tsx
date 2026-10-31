import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CircleDashedIcon,
  ExternalLinkIcon,
  KeyRoundIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useClearCredentials,
  useSaveCredentials,
  useSetPortalEnabled,
  type PortalView,
} from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import { coverage, fieldLabel, plural, timeAgo } from "./sourceText";

const RISK = {
  low: { label: "Low risk", hint: "Official public API or feed", icon: ShieldCheckIcon },
  medium: { label: "Medium risk", hint: "Unofficial access; may break", icon: ShieldAlertIcon },
  high: { label: "High risk", hint: "Breaks the site's terms", icon: ShieldAlertIcon },
} as const;

function RiskBadge({ level }: { level: PortalView["risk_level"] }) {
  const risk = RISK[level];
  return (
    <Badge
      variant="outline"
      title={risk.hint}
      className={cn(level === "high" && "border-destructive/50 text-destructive")}
    >
      <risk.icon aria-hidden /> {risk.label}
    </Badge>
  );
}

function StatusLine({ portal }: { portal: PortalView }) {
  if (!portal.ready) {
    return (
      <p className="flex items-start gap-1.5 text-sm text-muted-foreground">
        <CircleDashedIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
        Needs {portal.missing.join(", ")}
      </p>
    );
  }
  if (portal.status === "error") {
    return (
      <p className="flex items-start gap-1.5 text-sm text-destructive">
        <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          Last search failed
          {portal.last_run_at && ` ${timeAgo(portal.last_run_at)}`}
          {portal.last_error && `: ${portal.last_error}`}
        </span>
      </p>
    );
  }
  return (
    <p className="flex items-start gap-1.5 text-sm text-muted-foreground">
      <CheckCircle2Icon className="mt-0.5 size-4 shrink-0 text-score-high" aria-hidden />
      {portal.last_run_at ? `Searched ${timeAgo(portal.last_run_at)}` : "Ready, not searched yet"}
    </p>
  );
}

/** Saved non-secret settings (e.g. the USAJOBS email) as form values. Secrets never come back. */
function configValues(portal: PortalView): Record<string, string> {
  return Object.fromEntries(
    portal.config_fields.map((f) => {
      const value = portal.config[f];
      return [f, typeof value === "string" ? value : ""] as const;
    }),
  );
}

function CredentialsForm({ portal }: { portal: PortalView }) {
  const fields = [...portal.secret_fields, ...portal.config_fields];
  const [values, setValues] = useState<Record<string, string>>(() => configValues(portal));
  const [editing, setEditing] = useState(!portal.ready);
  const save = useSaveCredentials();
  const clear = useClearCredentials();
  const formId = useId();

  if (!editing) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <KeyRoundIcon className="size-4 text-muted-foreground" aria-hidden />
        <span className="text-muted-foreground">Key saved in your keychain</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setEditing(true);
          }}
        >
          Replace
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={clear.isPending}
          onClick={() => {
            clear.mutate(portal.id, {
              onSuccess: () => {
                toast(`${portal.name} key removed`);
                setEditing(true);
              },
              onError: (error) => toast.error(errorText(error, "Couldn't remove the key")),
            });
          }}
        >
          Remove
        </Button>
      </div>
    );
  }

  const complete = fields.every((f) => (values[f] ?? "").trim().length > 0);
  return (
    <form
      className="space-y-3"
      aria-label={`${portal.name} API key`}
      onSubmit={(event) => {
        event.preventDefault();
        const pick = (keys: string[]) =>
          Object.fromEntries(keys.map((k) => [k, (values[k] ?? "").trim()] as const));
        save.mutate(
          {
            id: portal.id,
            secrets: pick(portal.secret_fields),
            config: pick(portal.config_fields),
          },
          {
            onSuccess: (updated) => {
              setValues(configValues(updated));
              if (updated.ready) setEditing(false);
              toast.success(`${portal.name} key saved`);
            },
            onError: (error) => toast.error(errorText(error, "Couldn't save the key")),
          },
        );
      }}
    >
      {fields.map((field) => {
        const secret = portal.secret_fields.includes(field);
        const id = `${formId}-${field}`;
        return (
          <div key={field} className="space-y-1">
            <Label htmlFor={id} className="text-xs">
              {fieldLabel(field)}
            </Label>
            <Input
              id={id}
              type={secret ? "password" : field === "email" ? "email" : "text"}
              autoComplete="off"
              spellCheck={false}
              value={values[field] ?? ""}
              onChange={(event) => {
                setValues((current) => ({ ...current, [field]: event.target.value }));
              }}
            />
          </div>
        );
      })}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="sm" disabled={!complete || save.isPending}>
          <KeyRoundIcon /> {save.isPending ? "Saving…" : "Save key"}
        </Button>
        <a
          href={portal.docs_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-sm text-primary-text underline-offset-4 hover:underline"
        >
          Get a free key <ExternalLinkIcon className="size-3.5" aria-hidden />
        </a>
      </div>
    </form>
  );
}

export function PortalCard({
  portal,
  onManageCompanies,
}: {
  portal: PortalView;
  onManageCompanies?: (ats: string) => void;
}) {
  const toggle = useSetPortalEnabled();
  const switchId = useId();
  const where = coverage(portal.countries);
  const needsKey = portal.secret_fields.length > 0;

  return (
    <Card className={cn("gap-4", !portal.enabled && "bg-muted/30")}>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="space-y-1.5">
          <CardTitle>
            <Label htmlFor={switchId} className="text-base font-semibold">
              {portal.name}
            </Label>
          </CardTitle>
          <div className="flex flex-wrap gap-1.5">
            <RiskBadge level={portal.risk_level} />
            {where && <Badge variant="secondary">{where}</Badge>}
          </div>
        </div>
        <Switch
          id={switchId}
          checked={portal.enabled}
          disabled={toggle.isPending}
          onCheckedChange={(enabled) => {
            toggle.mutate(
              { id: portal.id, enabled },
              { onError: (error) => toast.error(errorText(error, "Couldn't update the source")) },
            );
          }}
        />
      </CardHeader>
      <CardContent className="space-y-3">
        <StatusLine portal={portal} />
        <dl className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
          <div className="flex gap-1.5">
            <dt className="text-muted-foreground">Jobs found</dt>
            <dd className="font-medium tabular-nums">{portal.jobs_found.toLocaleString("en")}</dd>
          </div>
          {portal.companies !== null && (
            <div className="flex items-center gap-1.5">
              <dt className="text-muted-foreground">Watching</dt>
              <dd>
                <Button
                  variant="link"
                  className="h-auto p-0 font-medium"
                  onClick={() => onManageCompanies?.(portal.id)}
                >
                  {plural(portal.companies, "company", "companies")}
                </Button>
              </dd>
            </div>
          )}
        </dl>
        {needsKey && <CredentialsForm portal={portal} />}
      </CardContent>
    </Card>
  );
}
