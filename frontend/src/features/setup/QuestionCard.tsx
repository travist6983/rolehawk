import { ArrowLeftIcon, CheckIcon, PlusIcon, XIcon } from "lucide-react";
import { type KeyboardEvent, useId, useState } from "react";

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
  canGoBack: boolean;
  onAnswer: (value: AnswerValue) => void;
  onSkip: () => void;
  onBack: () => void;
}

/** Questions that collect several items: chips, plus a box that adds more with Enter. */
function collectsItems(question: Question): boolean {
  return question.kind === "multi" || question.kind === "list";
}

function splitItems(text: string): string[] {
  return text
    .split(/[,\n]/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function isChoice(question: Question, value: string): boolean {
  return question.choices.some((choice) => choice.value === value);
}

/** The text box's starting value. A saved single answer shows there only when it isn't one of
 * the choices (a typed "other"); item lists start as chips instead. */
function initialText(question: Question): string {
  const { value } = question;
  if (collectsItems(question)) return "";
  if (question.kind === "single") {
    return typeof value === "string" && !isChoice(question, value) ? value : "";
  }
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.join(", ");
  return "";
}

/** Saved items (multi and list questions start with them selected). */
function initialItems(question: Question): string[] {
  const { value } = question;
  if (Array.isArray(value)) return value;
  if (typeof value === "string") return splitItems(value);
  return [];
}

type FormValues = Record<string, string | string[]>;

/** A form starts from the saved answer; list fields (links) always show at least one box. */
function initialForm(question: Question): FormValues {
  const saved = question.value && typeof question.value === "object" ? question.value : {};
  const values = Array.isArray(saved) ? {} : saved;
  const form: FormValues = {};
  for (const field of question.fields) {
    const value = values[field.name];
    if (field.kind === "list") {
      const items = Array.isArray(value) ? value : value ? [value] : [];
      form[field.name] = items.length > 0 ? [...items] : [""];
    } else if (typeof value === "string") {
      form[field.name] = value;
    }
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

/** Enter in a box that collects items adds them; it never submits the question. */
function enterAdds(event: KeyboardEvent<HTMLInputElement>, add: () => void) {
  if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
  event.preventDefault();
  add();
}

/** One interview question. Remount it per question (see InterviewStep's key) to reset it. */
export function QuestionCard({
  question,
  pending,
  error,
  canGoBack,
  onAnswer,
  onSkip,
  onBack,
}: QuestionCardProps) {
  const promptId = useId();
  const errorId = useId();
  const [text, setText] = useState(() => initialText(question));
  const [selected, setSelected] = useState<string[]>(() => initialItems(question));
  // Items typed in (not among the choices), shown as chips after the choices.
  const [added, setAdded] = useState<string[]>(() =>
    initialItems(question).filter((item) => !isChoice(question, item)),
  );
  const [form, setForm] = useState<FormValues>(() => initialForm(question));

  const chips = [...question.choices, ...added.map((item) => ({ value: item, label: item }))];

  const addTyped = () => {
    const items = splitItems(text);
    if (items.length === 0) return;
    const known = new Set(chips.map((chip) => chip.value.toLowerCase()));
    const values = items.map(
      (item) =>
        chips.find((chip) => chip.value.toLowerCase() === item.toLowerCase())?.value ?? item,
    );
    setAdded([...added, ...items.filter((item) => !known.has(item.toLowerCase()))]);
    setSelected([...selected, ...values.filter((value) => !selected.includes(value))]);
    setText("");
  };

  const submit = () => {
    if (collectsItems(question)) {
      const typed = splitItems(text).filter((item) => !selected.includes(item));
      onAnswer([...selected, ...typed]);
    } else if (question.kind === "form") {
      onAnswer(formAnswer(form));
    } else {
      onAnswer(text);
    }
  };

  const canSubmit =
    !pending &&
    (collectsItems(question)
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
        // Choosing an option answers immediately, so these are plain buttons in a group. After
        // Back, the saved answer is marked.
        <div role="group" aria-labelledby={promptId} className="grid gap-2 sm:grid-cols-2">
          {question.choices.map((choice) => {
            const saved = choice.value === question.value;
            return (
              <button
                key={choice.value}
                type="button"
                disabled={pending}
                aria-pressed={saved}
                onClick={() => {
                  onAnswer(choice.value);
                }}
                className={cn(
                  "flex items-center justify-between gap-2 rounded-lg border bg-card px-4 py-3 text-left text-sm font-medium transition-colors duration-150 hover:border-primary hover:bg-primary/5 disabled:opacity-50",
                  saved && "border-primary bg-primary/5",
                )}
              >
                {choice.label}
                {saved && <CheckIcon className="size-4 shrink-0 text-primary" aria-hidden />}
              </button>
            );
          })}
        </div>
      )}

      {collectsItems(question) && chips.length > 0 && (
        <div className="flex flex-wrap gap-2" role="group" aria-labelledby={promptId}>
          {chips.map((chip) => {
            const on = selected.includes(chip.value);
            return (
              <button
                key={chip.value}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setSelected(
                    on ? selected.filter((v) => v !== chip.value) : [...selected, chip.value],
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
                {chip.label}
              </button>
            );
          })}
        </div>
      )}

      {collectsItems(question) && (question.kind === "list" || question.allow_other) && (
        <div className="space-y-1.5">
          {question.kind === "multi" && (
            <Label htmlFor={`${promptId}-text`} className="text-muted-foreground">
              Add your own
            </Label>
          )}
          <div className="flex gap-2">
            <Input
              id={`${promptId}-text`}
              autoComplete="off"
              aria-labelledby={question.kind === "list" ? promptId : undefined}
              aria-describedby={described}
              value={text}
              placeholder={question.placeholder ?? undefined}
              onChange={(e) => {
                setText(e.target.value);
              }}
              onKeyDown={(e) => {
                enterAdds(e, addTyped);
              }}
              autoFocus
            />
            <Button type="button" variant="outline" disabled={!text.trim()} onClick={addTyped}>
              <PlusIcon aria-hidden />
              Add
            </Button>
          </div>
        </div>
      )}

      {(question.kind === "text" || (question.allow_other && question.kind === "single")) && (
        <div className="space-y-1.5">
          {question.allow_other && (
            <Label htmlFor={`${promptId}-text`} className="text-muted-foreground">
              Or type your own
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
        {canGoBack && (
          <Button type="button" variant="ghost" disabled={pending} onClick={onBack}>
            <ArrowLeftIcon aria-hidden />
            Back
          </Button>
        )}
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

/** One box per item, a button to add another, and a remove button on each extra box. Enter in
 * a filled box moves to an empty one (adding it if needed) instead of submitting. */
function ListField({ id, label, placeholder, items, describedBy, onChange }: ListFieldProps) {
  const labelId = `${id}-label`;
  const [focusLast, setFocusLast] = useState(false);
  const addBox = () => {
    const last = items.length - 1;
    if (items[last]?.trim() === "") {
      document.getElementById(`${id}-${last}`)?.focus();
      return;
    }
    setFocusLast(true);
    onChange([...items, ""]);
  };
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
                onKeyDown={(e) => {
                  enterAdds(e, () => {
                    if (item.trim()) addBox();
                  });
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
