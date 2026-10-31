import type { ComponentType } from "react";

import type { ChatCard } from "../types";

type CardOf<T extends string> = Extract<ChatCard, { type: T }>;
export type AnyCardComponent = ComponentType<{ card: ChatCard }>;

const registry = new Map<string, AnyCardComponent>();

/** Register the component for one card type. Features register their own cards, so the chat
 *  drawer never needs to know about every feature. */
export function registerCard<T extends ChatCard["type"]>(
  type: T,
  component: ComponentType<{ card: CardOf<T> }>,
): void {
  // Safe: CardRenderer only passes cards whose `type` matched this key.
  registry.set(type, component as unknown as AnyCardComponent);
}

export function cardComponent(type: string): AnyCardComponent | undefined {
  return registry.get(type);
}
