import { createElement } from "react";

import type { ChatCard } from "../types";
import { cardComponent } from "./registry";

export function FallbackCard({ card }: { card: ChatCard }) {
  return (
    <details className="rounded-lg border bg-muted/40 p-3 text-xs">
      <summary className="cursor-pointer font-medium">{card.type.replace(/_/g, " ")}</summary>
      <pre className="mt-2 overflow-x-auto font-mono whitespace-pre-wrap">
        {JSON.stringify(card, null, 2)}
      </pre>
    </details>
  );
}

/** Renders a card with its registered component (module-level, so identity is stable). */
export function CardRenderer({ card }: { card: ChatCard }) {
  return createElement(cardComponent(card.type) ?? FallbackCard, { card });
}
