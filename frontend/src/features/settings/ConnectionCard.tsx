import { CheckCircle2Icon, ExternalLinkIcon, KeyRoundIcon, TerminalIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useClearApiKey, useSetApiKey, type LLMStatus } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const CONSOLE_KEYS_URL = "https://console.anthropic.com/settings/keys";

export function ConnectionCard({ status }: { status: LLMStatus }) {
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
            className="inline-flex items-center gap-1 text-primary-text underline-offset-4 hover:underline"
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
