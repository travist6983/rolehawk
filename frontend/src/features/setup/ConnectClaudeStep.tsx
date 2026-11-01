import {
  CheckCircle2Icon,
  ChevronDownIcon,
  ExternalLinkIcon,
  FlaskConicalIcon,
  KeyRoundIcon,
  TerminalIcon,
} from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useSetApiKey,
  useTestApiKey,
  useUpdateLLMSettings,
  type KeyTest,
  type LLMStatus,
} from "@/api/queries";
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
import { KeyTestResult } from "@/features/settings/KeyTestResult";
import { TypicalCostNote } from "@/features/settings/TypicalCostNote";
import { cn } from "@/lib/utils";
import { PRODUCT_NAME } from "@/lib/brand";

import { ConsoleIllustration, type ConsolePage } from "./ConsoleIllustration";

function Step({
  n,
  title,
  link,
  illustration,
  children,
}: {
  n: number;
  title: string;
  link?: { href: string; label: string };
  illustration?: ConsolePage;
  children?: React.ReactNode;
}) {
  const [showing, setShowing] = useState(false);
  const drawingId = useId();
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
        {illustration && (
          <div className="space-y-2">
            <button
              type="button"
              aria-expanded={showing}
              aria-controls={drawingId}
              onClick={() => {
                setShowing((value) => !value);
              }}
              className="flex items-center gap-1 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              <ChevronDownIcon
                aria-hidden
                className={cn(
                  "size-3.5 transition-transform motion-reduce:transition-none",
                  showing && "rotate-180",
                )}
              />
              {showing ? "Hide the picture" : "Show me what this looks like"}
            </button>
            <div id={drawingId} hidden={!showing}>
              {showing && <ConsoleIllustration page={illustration} />}
            </div>
          </div>
        )}
      </div>
    </li>
  );
}

/** First-run walkthrough for people who've never made an API key. */
export function ConnectClaudeStep({
  status,
  onContinue,
  onStay,
  onUseClaudeCode,
}: {
  status: LLMStatus;
  onContinue: () => void;
  /** Keep setup on this step even after the key is saved. */
  onStay: () => void;
  onUseClaudeCode: () => void;
}) {
  const [key, setKey] = useState("");
  const [cap, setCap] = useState<number | null>(
    status.monthly_cap_usd === null ? DEFAULT_CAP : status.monthly_cap_usd,
  );
  // The latest test result, from Connect or from Test again.
  const [result, setResult] = useState<KeyTest | null>(null);
  const setApiKey = useSetApiKey();
  const testKey = useTestApiKey();
  const updateSettings = useUpdateLLMSettings();
  const keyId = useId();

  const runTest = () => {
    testKey.mutate(undefined, {
      onSuccess: setResult,
      onError: (error) => toast.error(errorText(error, "Couldn't run the test. Try again.")),
    });
  };

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
        {result && <KeyTestResult result={result} />}
        <div className="flex flex-wrap gap-2">
          <Button onClick={onContinue}>
            {result && !result.ok ? "Continue anyway" : "Continue"}
          </Button>
          <Button variant="outline" onClick={runTest} disabled={testKey.isPending}>
            <FlaskConicalIcon />{" "}
            {testKey.isPending ? "Testing…" : result ? "Test again" : "Test key"}
          </Button>
        </div>
      </div>
    );
  }

  const save = () => {
    setResult(null);
    // Saving marks Claude as connected, which would move setup on before the test result
    // shows; pin this step first so a problem's fix stays on screen.
    onStay();
    setApiKey.mutate(key.trim(), {
      onSuccess: ({ saved, test }) => {
        if (!saved) {
          setResult(test);
          return;
        }
        setKey("");
        if (cap !== status.monthly_cap_usd) {
          updateSettings.mutate({ monthly_cap_usd: cap });
        }
        if (test.ok) {
          toast.success("Claude is connected and working");
          onContinue();
        } else {
          // Saved, but the account can't run requests yet: the connected view shows the fix.
          setResult(test);
        }
      },
      onError: (error) =>
        toast.error(errorText(error, "Couldn't check the key. Try again in a moment.")),
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
          <TypicalCostNote cost={status.typical_cost} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Get your key (about 5 minutes)</CardTitle>
          <CardDescription>
            You'll use Anthropic's Claude Platform, the website where developers manage Claude. You
            don't need to be a developer: it's four short steps, and each link opens the right page
            in a new tab.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-5 text-sm" aria-label="Steps to connect Claude">
            <Step
              n={1}
              title="Create a Claude Platform account"
              link={{ href: CLAUDE_PLATFORM_URL, label: "Open the Claude Platform" }}
              illustration="signup"
            >
              <p className="text-muted-foreground">
                Sign up with Google or your email; it's free. This is separate from a claude.ai
                subscription, though you can use the same email. If it asks for an organization
                name, your own name is fine.
              </p>
            </Step>
            <Step
              n={2}
              title="Add some credit"
              link={{ href: CLAUDE_BILLING_URL, label: "Open Billing" }}
              illustration="billing"
            >
              <p className="text-muted-foreground">
                Choose <span className="font-medium text-foreground">Buy credits</span> and add $10
                to $20 with a card; that covers a few weeks of typical use. If you see an option to
                reload credit automatically, you can leave it off, so you're never charged more than
                you added.
              </p>
              <p className="text-muted-foreground">
                For extra peace of mind, scroll to{" "}
                <span className="font-medium text-foreground">Spend limits</span> on the same page
                and choose <span className="font-medium text-foreground">Set limit</span>. That caps
                your whole account, whatever uses it.
              </p>
            </Step>
            <Step
              n={3}
              title="Create a key and copy it"
              link={{ href: CLAUDE_KEYS_URL, label: "Open API keys" }}
              illustration="keys"
            >
              <p className="text-muted-foreground">
                Choose <span className="font-medium text-foreground">Create key</span>, name it
                &ldquo;{PRODUCT_NAME}&rdquo;, keep the Default workspace, and copy the key. It
                starts with <code className="rounded bg-muted px-1">sk-ant-</code> and is shown only
                once. If you lose it, just make another one.
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
                    {PRODUCT_NAME} stops new AI work when the month's spending reaches this limit.
                    You can change it any time in Settings.
                  </p>
                </fieldset>
                {result && <KeyTestResult result={result} />}
                <Button type="submit" disabled={key.trim().length < 10 || setApiKey.isPending}>
                  <KeyRoundIcon /> {setApiKey.isPending ? "Testing the key…" : "Connect and test"}
                </Button>
                <p className="text-xs text-muted-foreground">
                  Connecting sends Claude one tiny test message, which costs a tiny fraction of a
                  cent, so you know straight away that everything works.
                </p>
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
