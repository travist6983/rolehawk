import { ArchiveRestoreIcon, Trash2Icon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useReset, useResetScopes, type ResetResult } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { PRODUCT_NAME } from "@/lib/brand";

type Scope = ResetResult["scope"];

function Summary({ result }: { result: ResetResult }) {
  const removed = Object.entries(result.removed)
    .filter(([, n]) => n > 0)
    .map(([what, n]) => `${String(n)} ${what}`);
  return (
    <div className="space-y-1 rounded-lg border p-3 text-sm" role="status">
      <p className="flex items-center gap-2 font-medium">
        <ArchiveRestoreIcon className="size-4 text-muted-foreground" aria-hidden /> Reset done.
      </p>
      <p className="text-muted-foreground">
        {removed.length > 0 ? `Removed ${removed.join(", ")}.` : "There was nothing to remove."}
      </p>
      <p className="break-all text-muted-foreground">
        Backup: <code className="font-mono text-xs">{result.backup}</code>
      </p>
    </div>
  );
}

export function ResetCard() {
  const scopes = useResetScopes();
  const reset = useReset();
  const [scope, setScope] = useState<Scope | null>(null);
  const [confirm, setConfirm] = useState("");
  const confirmId = useId();
  const chosen = scopes.data?.find((s) => s.id === scope);
  const matches = scope !== null && confirm.trim().toLowerCase() === scope;

  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle>Reset</CardTitle>
        <CardDescription>
          Start over, in part or in full. {PRODUCT_NAME} zips a backup of your data folder first, so
          nothing is lost for good. Settings and API keys always stay.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">What to reset</legend>
          {(scopes.data ?? []).map((s) => {
            const id = `${confirmId}-${s.id}`;
            return (
              <div
                key={s.id}
                className={cn(
                  "flex gap-3 rounded-lg border p-3 has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50",
                  scope === s.id && "border-destructive/60 bg-destructive/5",
                )}
              >
                <input
                  id={id}
                  type="radio"
                  name="reset-scope"
                  value={s.id}
                  checked={scope === s.id}
                  className="mt-1 accent-destructive"
                  onChange={() => {
                    setScope(s.id);
                    setConfirm("");
                    reset.reset();
                  }}
                />
                <label htmlFor={id} className="cursor-pointer text-sm">
                  <span className="font-medium">{s.label}</span>
                  <span className="block text-muted-foreground">{s.description}</span>
                </label>
              </div>
            );
          })}
        </fieldset>
        {chosen && (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (!matches) return;
              reset.mutate(
                { scope: chosen.id, confirm },
                {
                  onSuccess: () => {
                    setConfirm("");
                    toast.success(`${chosen.label} reset`);
                  },
                  onError: (error) => toast.error(errorText(error, "Couldn't reset")),
                },
              );
            }}
          >
            <div className="min-w-48 flex-1 space-y-1.5">
              <Label htmlFor={confirmId}>
                Type <span className="font-mono">{chosen.id}</span> to confirm
              </Label>
              <Input
                id={confirmId}
                autoComplete="off"
                spellCheck={false}
                value={confirm}
                onChange={(event) => {
                  setConfirm(event.target.value);
                }}
              />
            </div>
            <Button type="submit" variant="destructive" disabled={!matches || reset.isPending}>
              <Trash2Icon />{" "}
              {reset.isPending
                ? "Backing up and resetting…"
                : `Reset ${chosen.label.toLowerCase()}`}
            </Button>
          </form>
        )}
        {reset.data && <Summary result={reset.data} />}
      </CardContent>
    </Card>
  );
}
