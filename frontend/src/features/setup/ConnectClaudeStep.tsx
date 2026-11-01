import {
  CheckCircle2Icon,
  CircleDollarSignIcon,
  ExternalLinkIcon,
  KeyRoundIcon,
  TerminalIcon,
} from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useSetApiKey, useUpdateLLMSettings, type LLMStatus } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CAP_CHOICES,
  CLAUDE_BILLING_URL,
  CLAUDE_KEYS_URL,
  CLAUDE_PLATFORM_URL,
  DEFAULT_CAP,
  capLabel,
} from "@/features/settings/claudeLinks";
import { cn } from "@/lib/utils";
import { PRODUCT_NAME } from "@/lib/brand";

function Step({
  n,
  title,
  link,
  children,
}: {
  n: number;
  title: string;
  link?: { href: string; label: string };
  children?: React.ReactNode;
}) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden
        className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary-text"
      >
        {n}
      </span>
      <div className="min-w-0 flex-1 space-y-1.5 pb-1">
        <p className="font-medium">{title}</p>
        {children}
        {link && (
          <a
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm text-primary-text underline-offset-4 hover:underline"
          >
            {link.label} <ExternalLinkIcon className="size-3.5" aria-hidden />
          </a>
        )}
      </div>
    </li>
  );
}

/** First-run walkthrough for people who've never made an API key. */
export function ConnectClaudeStep({
  status,
  onContinue,
  onUseClaudeCode,
}: {
  status: LLMStatus;
  onContinue: () => void;
  onUseClaudeCode: () => void;
}) {
  const [key, setKey] = useState("");
  const [cap, setCap] = useState<number | null>(
    status.monthly_cap_usd === null ? DEFAULT_CAP : status.monthly_cap_usd,
  );
  const setApiKey = useSetApiKey();
  const updateSettings = useUpdateLLMSettings();
  const keyId = useId();

  if (status.configured) {
    return (
      <div className="space-y-4">
        <Card>
          <CardContent className="flex gap-3 pt-6 text-sm">
            <CheckCircle2Icon aria-hidden className="mt-0.5 size-5 shrink-0 text-score-high" />
            <div>
              <p className="font-medium">Claude is connected.</p>
              <p className="text-muted-foreground">
                {status.monthly_cap_usd === null
                  ? "No monthly limit is set; you can add one in Settings."
                  : `New AI work stops at $${status.monthly_cap_usd.toFixed(2)} a month; change it in Settings.`}
              </p>
            </div>
          </CardContent>
        </Card>
        <Button onClick={onContinue}>Continue</Button>
      </div>
    );
  }

  const save = () => {
    setApiKey.mutate(key.trim(), {
      onSuccess: () => {
        setKey("");
        if (cap !== status.monthly_cap_usd) {
          updateSettings.mutate({ monthly_cap_usd: cap });
        }
        toast.success("Claude is connected");
        onContinue();
      },
      onError: (error) =>
        toast.error(
          errorText(error, "That key didn't work. Check you copied all of it, then try again."),
        ),
    });
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Connect Claude</CardTitle>
          <CardDescription>
            {PRODUCT_NAME} uses Claude to rank jobs and write your applications. It connects with an{" "}
            <span className="font-medium text-foreground">API key</span>: a long password that lets
            this app use Claude on your account. You pay Anthropic only for what you use, and the
            key is stored in your computer's keychain, never in a file.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-3 rounded-lg bg-muted/50 p-3 text-sm">
            <CircleDollarSignIcon
              aria-hidden
              className="mt-0.5 size-4 shrink-0 text-muted-foreground"
            />
            <p>
              <span className="font-medium">About $12 to $25 a month</span> for an active search
              (ranking 50 jobs and writing 10 applications a week), $3 to $6 for light use. Every
              big task shows its cost before it runs. A Claude Pro or Max subscription can't be used
              by other apps, so this is billed separately on the Claude Platform.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Get your key (about 5 minutes)</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-4 text-sm" aria-label="Steps to connect Claude">
            <Step
              n={1}
              title="Create a Claude Platform account"
              link={{ href: CLAUDE_PLATFORM_URL, label: "Open the Claude Platform" }}
            >
              <p className="text-muted-foreground">
                It's free to sign up, and separate from claude.ai (you can use the same email).
              </p>
            </Step>
            <Step
              n={2}
              title="Add some credit"
              link={{ href: CLAUDE_BILLING_URL, label: "Open Billing" }}
            >
              <p className="text-muted-foreground">
                Buy a small amount of credit to start; $10 to $20 covers a few weeks of typical use.
              </p>
            </Step>
            <Step
              n={3}
              title="Create a key and copy it"
              link={{ href: CLAUDE_KEYS_URL, label: "Open API keys" }}
            >
              <p className="text-muted-foreground">
                Choose Create key, name it &ldquo;{PRODUCT_NAME}&rdquo;, and copy it. It starts with{" "}
                <code className="rounded bg-muted px-1">sk-ant-</code> and is shown only once.
              </p>
            </Step>
            <Step n={4} title="Paste it here and choose a monthly limit">
              <form
                className="space-y-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  save();
                }}
              >
                <div className="space-y-1.5">
                  <Label htmlFor={keyId}>Your API key</Label>
                  <Input
                    id={keyId}
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
                <fieldset className="space-y-1.5">
                  <legend className="text-sm font-medium">Monthly limit</legend>
                  <div
                    className="flex flex-wrap gap-2"
                    role="radiogroup"
                    aria-label="Monthly limit"
                  >
                    {CAP_CHOICES.map((choice) => (
                      <button
                        key={String(choice)}
                        type="button"
                        role="radio"
                        aria-checked={cap === choice}
                        onClick={() => {
                          setCap(choice);
                        }}
                        className={cn(
                          "rounded-md border px-3 py-1.5 text-sm",
                          cap === choice ? "border-primary bg-primary/5" : "hover:bg-muted",
                        )}
                      >
                        {capLabel(choice)}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    New AI work stops when the month's spending reaches the limit. You can change it
                    any time in Settings.
                  </p>
                </fieldset>
                <Button type="submit" disabled={key.trim().length < 10 || setApiKey.isPending}>
                  <KeyRoundIcon /> {setApiKey.isPending ? "Checking the key…" : "Connect"}
                </Button>
              </form>
            </Step>
          </ol>
        </CardContent>
      </Card>

      <div className="flex gap-3 rounded-lg border p-3 text-sm">
        <TerminalIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <div className="space-y-2">
          <p>
            <span className="font-medium">Use Claude Code?</span>{" "}
            <span className="text-muted-foreground">
              If you already work in Claude Code, it can run {PRODUCT_NAME}'s commands with your
              subscription instead, and you can skip this.
            </span>
          </p>
          <Button variant="outline" size="sm" onClick={onUseClaudeCode}>
            I'll use Claude Code instead
          </Button>
        </div>
      </div>
    </div>
  );
}
