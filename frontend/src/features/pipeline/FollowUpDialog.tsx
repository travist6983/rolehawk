import { AlertTriangleIcon, CopyIcon, MailCheckIcon, SparklesIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useDraftFollowUp,
  useLogFollowUp,
  type BoardCard,
  type FollowUpChannel,
} from "@/api/queries";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { CHANNELS, followUpText } from "./pipelineText";
import { PRODUCT_NAME } from "@/lib/brand";

type Channel = NonNullable<FollowUpChannel>;

/** Draft a follow-up from what was sent, edit it, copy it, and log it once sent. */
export function FollowUpDialog({ card, onClose }: { card: BoardCard; onClose: () => void }) {
  const id = useId();
  const [channel, setChannel] = useState<Channel>("email");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [issues, setIssues] = useState<string[]>([]);
  const draft = useDraftFollowUp(card.application_id);
  const log = useLogFollowUp(card.application_id);
  const drafted = body.trim().length > 0;

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Follow up with {card.company}</DialogTitle>
          <DialogDescription>
            {followUpText(card)} The draft uses only what you already sent them. {PRODUCT_NAME}{" "}
            never sends anything: copy it, send it yourself, then log it here.
          </DialogDescription>
        </DialogHeader>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Where will you send it?</legend>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Channel">
            {CHANNELS.map((option) => (
              <Button
                key={option.value}
                type="button"
                size="sm"
                variant={channel === option.value ? "default" : "outline"}
                role="radio"
                aria-checked={channel === option.value}
                onClick={() => {
                  setChannel(option.value);
                }}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </fieldset>
        <Button
          variant="outline"
          disabled={draft.isPending}
          onClick={() => {
            draft.mutate(channel, {
              onSuccess: (result) => {
                setSubject(result.subject ?? "");
                setBody(result.body);
                setIssues(result.issues);
              },
              onError: (error) => toast.error(errorText(error, "Couldn't write a draft")),
            });
          }}
        >
          <SparklesIcon />{" "}
          {draft.isPending ? "Writing…" : drafted ? "Write another" : "Write a draft"}
        </Button>
        {channel === "email" && (
          <div className="space-y-1">
            <Label htmlFor={`${id}-subject`}>Subject</Label>
            <Input
              id={`${id}-subject`}
              value={subject}
              maxLength={300}
              onChange={(event) => {
                setSubject(event.target.value);
              }}
            />
          </div>
        )}
        <div className="space-y-1">
          <Label htmlFor={`${id}-body`}>Message</Label>
          <Textarea
            id={`${id}-body`}
            rows={7}
            value={body}
            maxLength={5000}
            placeholder="Write a draft, or type your own."
            onChange={(event) => {
              setBody(event.target.value);
            }}
          />
          <p className="text-xs text-muted-foreground">
            {body.trim()
              ? `${String(body.trim().split(/\s+/).length)} words`
              : "Aim for 60-120 words."}
          </p>
        </div>
        {issues.length > 0 && (
          <ul className="space-y-1 text-xs text-caution" aria-label="Check before sending">
            {issues.map((issue) => (
              <li key={issue} className="flex gap-1.5">
                <AlertTriangleIcon aria-hidden className="mt-0.5 size-3.5 shrink-0" /> {issue}
              </li>
            ))}
          </ul>
        )}
        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            disabled={!drafted}
            onClick={() => {
              const text = channel === "email" && subject ? `${subject}\n\n${body}` : body;
              navigator.clipboard.writeText(text).then(
                () => toast.success("Copied"),
                () => toast.error("Couldn't copy; select the text instead"),
              );
            }}
          >
            <CopyIcon /> Copy
          </Button>
          <Button
            disabled={!drafted || log.isPending}
            onClick={() => {
              log.mutate(
                { channel, subject: channel === "email" ? subject || null : null, body },
                {
                  onSuccess: () => {
                    toast.success("Logged. The quiet-days count starts again.");
                    onClose();
                  },
                  onError: (error) => toast.error(errorText(error, "Couldn't log it")),
                },
              );
            }}
          >
            <MailCheckIcon /> I sent it
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
