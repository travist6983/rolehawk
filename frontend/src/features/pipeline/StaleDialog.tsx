import { ArchiveIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useCloseStale, type QuietApplication } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** Close applications that never got a reply, the ones the user picks, as Ghosted. */
export function StaleDialog({
  applications,
  onClose,
}: {
  applications: QuietApplication[];
  onClose: () => void;
}) {
  const [picked, setPicked] = useState<Set<number>>(
    () => new Set(applications.map((a) => a.application_id)),
  );
  const close = useCloseStale();

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Applications with no reply</DialogTitle>
          <DialogDescription>
            Quiet for 60 days or more. Closing them as no response keeps your pipeline and response
            rates honest. You can move one back any time.
          </DialogDescription>
        </DialogHeader>
        <ul className="max-h-80 space-y-2 overflow-y-auto" aria-label="Quiet applications">
          {applications.map((app) => {
            const id = `stale-${String(app.application_id)}`;
            return (
              <li key={app.application_id} className="flex items-start gap-2 text-sm">
                <Checkbox
                  id={id}
                  checked={picked.has(app.application_id)}
                  onCheckedChange={(checked) => {
                    setPicked((current) => {
                      const next = new Set(current);
                      if (checked === true) next.add(app.application_id);
                      else next.delete(app.application_id);
                      return next;
                    });
                  }}
                />
                <label htmlFor={id} className="min-w-0">
                  <span className="block truncate font-medium">{app.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {app.company} · no reply in {app.quiet_days} days ·{" "}
                    {app.follow_ups === 0
                      ? "no follow-ups"
                      : `${String(app.follow_ups)} follow-up${app.follow_ups === 1 ? "" : "s"}`}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={picked.size === 0 || close.isPending}
            onClick={() => {
              close.mutate([...picked], {
                onSuccess: (result) => {
                  toast.success(
                    `Closed ${String(result.closed)} as no response (moved to Ghosted).`,
                  );
                  onClose();
                },
                onError: (error) => toast.error(errorText(error, "Couldn't close them")),
              });
            }}
          >
            <ArchiveIcon /> Close {picked.size} as no response
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
