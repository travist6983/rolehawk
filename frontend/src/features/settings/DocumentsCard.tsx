import { CheckIcon, DownloadIcon, EyeIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  templatePreviewUrl,
  useDocumentSettings,
  useUpdateDocumentSettings,
  type DocumentSettings,
  type DocumentTemplate,
} from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const PAPER_LABELS = { letter: "Letter", a4: "A4" } as const;

function TemplatePicker({
  legend,
  name,
  templates,
  value,
  disabled,
  onChange,
  onPreview,
}: {
  legend: string;
  name: string;
  templates: DocumentTemplate[];
  value: string;
  disabled: boolean;
  onChange: (id: string) => void;
  onPreview: (template: DocumentTemplate) => void;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">{legend}</legend>
      <div className="grid gap-3 sm:grid-cols-3">
        {templates.map((template) => {
          const checked = template.id === value;
          const inputId = `${name}-${template.id}`;
          return (
            <div
              key={template.id}
              className={cn(
                "relative flex flex-col gap-2 rounded-lg border p-3 transition-colors has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50",
                checked ? "border-primary bg-primary/5" : "hover:bg-muted/50",
              )}
            >
              <input
                id={inputId}
                type="radio"
                name={name}
                value={template.id}
                checked={checked}
                disabled={disabled}
                className="peer sr-only"
                onChange={() => {
                  onChange(template.id);
                }}
              />
              <label htmlFor={inputId} className="cursor-pointer space-y-1">
                <span className="flex items-center gap-1.5 text-sm font-medium">
                  {template.name}
                  {checked && <CheckIcon className="size-4 text-primary" aria-hidden />}
                </span>
                <span className="block text-xs text-muted-foreground">{template.description}</span>
              </label>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="mt-auto w-fit px-2"
                aria-label={`Preview ${template.name}`}
                onClick={() => {
                  onPreview(template);
                }}
              >
                <EyeIcon /> Preview
              </Button>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}

function PreviewDialog({
  template,
  onClose,
}: {
  template: DocumentTemplate | null;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={template !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="flex h-[90dvh] max-w-4xl flex-col sm:max-w-4xl">
        {template && (
          <>
            <DialogHeader>
              <DialogTitle>{template.name} preview</DialogTitle>
              <DialogDescription>
                {template.kind === "cv"
                  ? "Filled with your profile (or a sample person until your profile has experience)."
                  : "Sample letter text with your contact details; /apply writes the real one for each job."}
              </DialogDescription>
            </DialogHeader>
            <iframe
              title={`${template.name} PDF preview`}
              src={templatePreviewUrl(template.id)}
              className="min-h-0 w-full flex-1 rounded-md border bg-white"
            />
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" asChild>
                <a href={templatePreviewUrl(template.id)} download={`${template.id}-preview.pdf`}>
                  <DownloadIcon /> PDF
                </a>
              </Button>
              <Button variant="outline" size="sm" asChild>
                <a
                  href={templatePreviewUrl(template.id, "docx")}
                  download={`${template.id}-preview.docx`}
                >
                  <DownloadIcon /> Word (DOCX)
                </a>
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DocumentsForm({ settings }: { settings: DocumentSettings }) {
  const update = useUpdateDocumentSettings();
  const [preview, setPreview] = useState<DocumentTemplate | null>(null);
  const paperId = useId();
  const save = (body: Parameters<typeof update.mutate>[0]) => {
    update.mutate(body, { onError: (error) => toast.error(errorText(error, "Couldn't save")) });
  };
  const cvTemplates = settings.templates.filter((t) => t.kind === "cv");
  const letterTemplates = settings.templates.filter((t) => t.kind === "cover_letter");

  return (
    <CardContent className="space-y-6">
      <TemplatePicker
        legend="CV template"
        name="cv-template"
        templates={cvTemplates}
        value={settings.cv_template}
        disabled={update.isPending}
        onChange={(id) => {
          save({ cv_template: id });
        }}
        onPreview={setPreview}
      />
      <TemplatePicker
        legend="Cover letter template"
        name="cover-template"
        templates={letterTemplates}
        value={settings.cover_template}
        disabled={update.isPending}
        onChange={(id) => {
          save({ cover_template: id });
        }}
        onPreview={setPreview}
      />
      <div className="max-w-xs space-y-1.5">
        <Label htmlFor={paperId}>Paper size</Label>
        <Select
          value={settings.paper_auto ? "auto" : settings.paper}
          onValueChange={(value) => {
            if (value === "auto" || value === "letter" || value === "a4") save({ paper: value });
          }}
        >
          <SelectTrigger id={paperId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">
              Automatic ({settings.paper_auto ? PAPER_LABELS[settings.paper] : "by country"})
            </SelectItem>
            <SelectItem value="letter">Letter</SelectItem>
            <SelectItem value="a4">A4</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <PreviewDialog
        template={preview}
        onClose={() => {
          setPreview(null);
        }}
      />
    </CardContent>
  );
}

export function DocumentsCard() {
  const settings = useDocumentSettings();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Documents</CardTitle>
        <CardDescription>
          Templates for the CVs and cover letters /apply creates, as Word and PDF. Every template is
          one column of real text with standard headings, so applicant tracking systems read it
          correctly.
        </CardDescription>
      </CardHeader>
      {settings.data ? (
        <DocumentsForm settings={settings.data} />
      ) : settings.isError ? (
        <CardContent>
          <p className="text-sm text-destructive">
            {errorText(settings.error, "Couldn't load document settings")}
          </p>
        </CardContent>
      ) : (
        <CardContent className="space-y-3" aria-label="Loading document settings">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      )}
    </Card>
  );
}
