import type { LucideIcon } from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";

export interface EmptyStep {
  title: string;
  description: string;
  action: { label: string; to: string } | { label: string; onClick: () => void };
}

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  /** Teaching empty states show the next steps, each a button (docs/SPEC.md design system). */
  steps?: EmptyStep[];
  children?: React.ReactNode;
}

export function EmptyState({ icon: Icon, title, description, steps, children }: EmptyStateProps) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-12 text-center">
      <span className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary">
        <Icon className="size-6" aria-hidden />
      </span>
      <h2 className="mt-4 text-lg font-semibold">{title}</h2>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
      {steps && (
        <ol className="mt-8 grid w-full gap-3 text-left sm:grid-cols-3">
          {steps.map((step, index) => (
            <li key={step.title} className="flex flex-col rounded-lg border bg-card p-4">
              <span className="font-mono text-xs font-semibold text-primary-text">
                Step {index + 1}
              </span>
              <span className="mt-1 font-medium">{step.title}</span>
              <span className="mt-1 flex-1 text-sm text-muted-foreground">{step.description}</span>
              {"to" in step.action ? (
                <Button
                  asChild
                  size="sm"
                  variant={index === 0 ? "default" : "outline"}
                  className="mt-3 self-start"
                >
                  <Link to={step.action.to}>{step.action.label}</Link>
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant={index === 0 ? "default" : "outline"}
                  className="mt-3 self-start"
                  onClick={step.action.onClick}
                >
                  {step.action.label}
                </Button>
              )}
            </li>
          ))}
        </ol>
      )}
      {children && <div className="mt-6">{children}</div>}
    </div>
  );
}
