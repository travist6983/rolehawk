import { PencilIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import { useSaveMemoryFile } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { PRODUCT_NAME } from "@/lib/brand";

type Target = "profile" | "preferences" | "facts";

/** A card that shows a memory file through `children` and edits its markdown in place. */
export function MemoryFileEditor({
  title,
  target,
  markdown,
  children,
}: {
  title: string;
  target: Target;
  markdown: string;
  children: React.ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(markdown);
  const save = useSaveMemoryFile();
  const editorId = useId();

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">{title}</CardTitle>
        {!editing && (
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Edit ${title.toLowerCase()}`}
            onClick={() => {
              setDraft(markdown);
              setEditing(true);
            }}
          >
            <PencilIcon /> Edit
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {editing ? (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate(
                { target, markdown: draft },
                {
                  onSuccess: () => {
                    setEditing(false);
                    toast.success(`${title} saved`);
                  },
                  onError: (error) => toast.error(errorText(error, "Couldn't save")),
                },
              );
            }}
          >
            <label htmlFor={editorId} className="text-xs text-muted-foreground">
              Markdown. Keep the ## headings so {PRODUCT_NAME} can read each section.
            </label>
            <Textarea
              id={editorId}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
              }}
              className="min-h-80 font-mono text-xs"
              spellCheck
            />
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={save.isPending || draft === markdown}>
                {save.isPending ? "Saving…" : "Save"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditing(false);
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}
