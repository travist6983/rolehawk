import { useQueryClient } from "@tanstack/react-query";
import { FileTextIcon, Loader2Icon, SparklesIcon, UploadIcon } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  setupKeys,
  useDraft,
  useLLMStatus,
  usePasteText,
  useStartExtraction,
  useUploadDocument,
  type DocumentView,
} from "@/api/queries";
import { FormSkeleton } from "@/components/feedback/Skeletons";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { TaskCard } from "@/features/chat/cards/cards";
import { useEventStream } from "@/features/events/EventStreamProvider";
import { cn } from "@/lib/utils";

import { DraftReview } from "./DraftReview";

const ACCEPT = ".pdf,.docx,.txt,.md,.zip";
const KIND_LABELS: Record<string, string> = {
  pdf: "PDF",
  docx: "Word",
  text: "Text",
  linkedin: "LinkedIn export",
};

function ExtractionProgress({ taskId, onFailed }: { taskId: string; onFailed: () => void }) {
  const task = useEventStream().task(taskId);
  const client = useQueryClient();
  const status = task?.status;
  useEffect(() => {
    if (status === "succeeded") void client.invalidateQueries({ queryKey: setupKeys.draft });
    if (status === "failed" || status === "cancelled") onFailed();
  }, [status, client, onFailed]);
  return <TaskCard card={{ task_id: taskId, command: "setup-extract" }} />;
}

export function ResumeStep({ onNext }: { onNext: () => void }) {
  const draft = useDraft();
  const status = useLLMStatus();
  const upload = useUploadDocument();
  const paste = usePasteText();
  const extract = useStartExtraction();
  const [docs, setDocs] = useState<DocumentView[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [failedTask, setFailedTask] = useState<string | null>(null);
  const [pasted, setPasted] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const pasteId = useId();
  const failed = useEventStream().task(failedTask ?? "");

  if (draft.isPending) return <FormSkeleton label="Loading" />;
  if (draft.data) {
    return <DraftReview key={draft.data.created_at} draft={draft.data} onApplied={onNext} />;
  }

  const addDocument = (doc: DocumentView) => {
    setDocs((current) => (current.some((d) => d.id === doc.id) ? current : [...current, doc]));
  };

  const uploadFiles = (files: FileList | null) => {
    for (const file of Array.from(files ?? [])) {
      upload.mutate(file, {
        onSuccess: addDocument,
        onError: (error) => toast.error(errorText(error, `Couldn't read ${file.name}`)),
      });
    }
  };

  const onlyLinkedIn = docs.length > 0 && docs.every((d) => d.kind === "linkedin");
  const needsClaude = docs.length > 0 && !onlyLinkedIn && status.data?.configured === false;

  return (
    <div className="space-y-6">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          uploadFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex flex-col items-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors duration-150",
          dragging ? "border-primary bg-primary/5" : "border-border",
        )}
      >
        <UploadIcon className="size-8 text-muted-foreground" aria-hidden />
        <div>
          <p className="font-medium">Drop your resume or LinkedIn export here</p>
          <p className="text-sm text-muted-foreground">
            PDF, Word (.docx), text, or the LinkedIn data ZIP · up to 10 MB
          </p>
        </div>
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          aria-label="Choose resume files"
          onChange={(event) => {
            uploadFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <Button
          type="button"
          variant="outline"
          disabled={upload.isPending}
          onClick={() => fileInput.current?.click()}
        >
          {upload.isPending ? <Loader2Icon className="animate-spin" /> : <FileTextIcon />}
          Choose files
        </Button>
      </div>

      <details className="rounded-lg border p-4">
        <summary className="cursor-pointer text-sm font-medium">Or paste your CV text</summary>
        <div className="mt-3 space-y-2">
          <Label htmlFor={pasteId} className="sr-only">
            CV text
          </Label>
          <Textarea
            id={pasteId}
            value={pasted}
            onChange={(e) => {
              setPasted(e.target.value);
            }}
            className="min-h-40"
            placeholder="Paste the full text of your CV"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!pasted.trim() || paste.isPending}
            onClick={() => {
              paste.mutate(pasted, {
                onSuccess: (doc) => {
                  addDocument(doc);
                  setPasted("");
                },
                onError: (error) => toast.error(errorText(error, "Couldn't use that text")),
              });
            }}
          >
            Use this text
          </Button>
        </div>
      </details>

      {docs.length > 0 && (
        <section aria-label="Your documents" className="space-y-3">
          <ul className="space-y-2">
            {docs.map((doc) => (
              <li
                key={doc.id}
                className="flex items-center gap-3 rounded-lg border bg-card px-3 py-2 text-sm"
              >
                <FileTextIcon className="size-4 text-muted-foreground" aria-hidden />
                <span className="flex-1 truncate">{doc.filename}</span>
                <span className="text-xs text-muted-foreground">
                  {KIND_LABELS[doc.kind] ?? doc.kind}
                </span>
              </li>
            ))}
          </ul>
          {taskId ? (
            <ExtractionProgress
              taskId={taskId}
              onFailed={() => {
                setFailedTask(taskId);
                setTaskId(null);
              }}
            />
          ) : (
            <Button
              disabled={extract.isPending || needsClaude}
              onClick={() => {
                setFailedTask(null);
                extract.mutate(
                  docs.map((d) => d.id),
                  {
                    onSuccess: (ref) => {
                      setTaskId(ref.task_id);
                    },
                    onError: (error) => toast.error(errorText(error, "Couldn't start reading")),
                  },
                );
              }}
            >
              <SparklesIcon />
              {onlyLinkedIn ? "Import" : "Read with Claude"}
            </Button>
          )}
          {needsClaude && (
            <p className="text-sm text-muted-foreground">
              Reading a resume needs Claude. Connect it in the first step, or skip and answer a few
              questions instead.
            </p>
          )}
          {failed?.error && (
            <p role="alert" className="text-sm text-destructive">
              {failed.error}
            </p>
          )}
        </section>
      )}

      <div className="border-t pt-4">
        <Button variant="ghost" onClick={onNext}>
          No resume? Answer a few questions instead
        </Button>
      </div>
    </div>
  );
}
