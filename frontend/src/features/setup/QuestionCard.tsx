import { CheckIcon, PlusIcon, XIcon } from "lucide-react";
import { useId, useState } from "react";

import type { AnswerValue, Question } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface QuestionCardProps {
  question: Question;
  pending: boolean;
  error: string | null;
  onAnswer: (value: AnswerValue) => void;
  onSkip: () => void;
}

function initialText(question: Question): string {
  const { value } = question;
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.join(", ");
  return "";
}

type FormValues = Record<string, string | string[]>;

/** List fields (links) start with one empty box; text fields start empty. */
function initialForm(question: Question): FormValues {
  const form: FormValues = {};
  for (const field of question.fields) {
    if (field.kind === "list") form[field.name] = [""];
  }
  return form;
}

/** What the form sends: list fields without their empty boxes. */
function formAnswer(form: FormValues): Record<string, string | string[]> {
  const answer: Record<string, string | string[]> = {};
  for (const [name, value] of Object.entries(form)) {
    answer[name] = Array.isArray(value) ? value.map((v) => v.trim()).filter(Boolean) : value;
  }
  return answer;
}

function filled(value: string | string[] | undefined): boolean {
  if (Array.isArray(value)) return value.some((v) => v.trim() !== "");
  return (value ?? "").trim() !== "";
}

function splitOther(text: string): string[] {
  return text
    .split(/[,\n]/)
    .map((part) => part.trim())
    .filter(Boolean);
}

/** One interview question. Remount it per question (key={question.id}) to reset its state. */
export function QuestionCard({ question, pending, error, onAnswer, onSkip }: QuestionCardProps) {
  const promptId = useId();
  const errorId = useId();
  const [text, setText] = useState(() => initialText(question));
  const [selected, setSelected] = useState<string[]>([]);
  const [form, setForm] = useState<FormValues>(() => initialForm(question));

  const submit = () => {
    switch (question.kind) {
      case "multi":
        onAnswer([...selected, ...splitOther(text)]);
        break;
      case "form":
        onAnswer(formAnswer(form));
        break;
      default:
        onAnswer(text);
    }
  };

  const canSubmit =
    !pending &&
    (question.kind === "multi"
      ? selected.length > 0 || text.trim() !== ""
      : question.kind === "form"
        ? question.fields.every((f) => !f.required || filled(form[f.name]))
        : text.trim() !== "");

  const described = error ? errorId : undefined;

  return (
    <form
      className="space-y-5"
      aria-labelledby={promptId}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) submit();
      }}
    >
      <div>
        <h2 id={promptId} className="text-xl font-semibold tracking-tight">
          {question.prompt}
        </h2>
        {question.help && <p className="mt-1 text-sm text-muted-foreground">{question.help}</p>}
      </div>

      {question.kind === "single" && (
        // Choosing an option answers immediately, so these are plain buttons in a group.
        <div role="group" aria-labelledby={promptId} className="grid gap-2 sm:grid-cols-2">
          {question.choices.map((choice) => (
            <button
              key={choice.value}
              type="button"
              disabled={pending}
              onClick={() => {
                onAnswer(choice.value);
              }}
              className="rounded-lg border bg-card px-4 py-3 text-left text-sm font-medium transition-colors duration-150 hover:border-primary hover:bg-primary/5 disabled:opacity-50"
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}

      {question.kind === "multi" && (
        <div className="flex flex-wrap gap-2" role="group" aria-labelledby={promptId}>
          {question.choices.map((choice) => {
            const on = selected.includes(choice.value);
            return (
              <button
                key={choice.value}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setSelected(
                    on ? selected.filter((v) => v !== choice.value) : [...selected, choice.value],
                  );
                }}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors duration-150",
                  on
                    ? "border-primary bg-primary/10 text-primary-text"
                    : "bg-card hover:border-primary",
                )}
              >
                {on && <CheckIcon className="size-3.5" aria-hidden />}
                {choice.label}
              </button>
            );
          })}
        </div>
      )}

      {(question.kind === "text" ||
        question.kind === "list" ||
        (question.allow_other && question.kind !== "form")) && (
        <div className="space-y-1.5">
          {question.allow_other && (
            <Label htmlFor={`${promptId}-text`} className="text-muted-foreground">
              {question.kind === "single" ? "Or type your own" : "Others (comma separated)"}
            </Label>
          )}
          {question.kind === "text" &&
          typeof question.value === "string" &&
          question.value.length > 60 ? (
            <Textarea
              id={`${promptId}-text`}
              aria-labelledby={question.allow_other ? undefined : promptId}
              aria-describedby={described}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
              }}
              className="min-h-24"
            />
          ) : (
            <div className="flex gap-2">
              <Input
                id={`${promptId}-text`}
                autoComplete="off"
                aria-labelledby={question.allow_other ? undefined : promptId}
                aria-describedby={described}
                value={text}
                placeholder={question.placeholder ?? undefined}
                onChange={(e) => {
                  setText(e.target.value);
                }}
                autoFocus
              />
              {question.kind === "single" && (
                <Button type="submit" variant="outline" disabled={!canSubmit}>
                  Use this
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      {question.kind === "form" && (
        <div className="grid gap-4 sm:grid-cols-2">
          {question.fields.map((field, index) => {
            const id = `${promptId}-${field.name}`;
            const current = form[field.name];
            const text = typeof current === "string" ? current : "";
            if (field.kind === "list") {
              return (
                <ListField
                  key={field.name}
                  id={id}
                  label={field.label}
                  placeholder={field.placeholder}
                  items={Array.isArray(current) ? current : [""]}
                  describedBy={described}
                  onChange={(items) => {
                    setForm({ ...form, [field.name]: items });
                  }}
                />
              );
            }
            const wide = field.kind === "textarea";
            return (
              <div key={field.name} className={cn("space-y-1.5", wide && "sm:col-span-2")}>
                <Label htmlFor={id}>
                  {field.label}
                  {field.required && (
                    <span aria-hidden className="text-destructive">
                      {" "}
                      *
                    </span>
                  )}
                </Label>
                {wide ? (
                  <Textarea
                    id={id}
                    value={text}
                    placeholder={field.placeholder ?? undefined}
                    onChange={(e) => {
                      setForm({ ...form, [field.name]: e.target.value });
                    }}
                    className="min-h-28"
                  />
                ) : (
                  <Input
                    id={id}
                    autoComplete="off"
                    required={field.required}
                    aria-describedby={described}
                    value={text}
                    placeholder={field.placeholder ?? undefined}
                    autoFocus={index === 0}
                    onChange={(e) => {
                      setForm({ ...form, [field.name]: e.target.value });
                    }}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {error && (
        <p id={errorId} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {question.kind !== "single" && (
          <Button type="submit" disabled={!canSubmit}>
            {pending ? "Saving…" : "Continue"}
          </Button>
        )}
        {question.optional && (
          <Button type="button" variant="ghost" disabled={pending} onClick={onSkip}>
            {question.skip_label}
          </Button>
        )}
      </div>
    </form>
  );
}

interface ListFieldProps {
  id: string;
  label: string;
  placeholder: string | null;
  items: string[];
  describedBy: string | undefined;
  onChange: (items: string[]) => void;
}

/** One box per item, a button to add another, and a remove button on each extra box. */
function ListField({ id, label, placeholder, items, describedBy, onChange }: ListFieldProps) {
  const labelId = `${id}-label`;
  const [focusLast, setFocusLast] = useState(false);
  return (
    <div role="group" aria-labelledby={labelId} className="space-y-2 sm:col-span-2">
      <Label id={labelId} htmlFor={`${id}-0`}>
        {label}
      </Label>
      <ul className="space-y-2">
        {items.map((item, index) => {
          const number = index + 1;
          return (
            // Items have no stable id; the index is the key, and removing rebuilds the list.
            <li key={index} className="flex gap-2">
              <Input
                id={`${id}-${index}`}
                inputMode="url"
                autoComplete="off"
                aria-label={items.length > 1 ? `Link ${number}` : undefined}
                aria-describedby={describedBy}
                value={item}
                placeholder={index === 0 ? (placeholder ?? undefined) : undefined}
                autoFocus={focusLast && index === items.length - 1}
                onChange={(e) => {
                  onChange(items.map((v, i) => (i === index ? e.target.value : v)));
                }}
              />
              {items.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove link ${number}`}
                  onClick={() => {
                    onChange(items.filter((_, i) => i !== index));
                  }}
                >
                  <XIcon aria-hidden />
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          setFocusLast(true);
          onChange([...items, ""]);
        }}
      >
        <PlusIcon aria-hidden />
        Add another link
      </Button>
    </div>
  );
}
