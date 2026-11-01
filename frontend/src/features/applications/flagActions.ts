/** What a flag's buttons can do, shared down the document editors without prop drilling. */

import { createContext, useContext } from "react";

import type { Flag, RegenerateSection } from "@/api/queries";

export interface RewriteAsk {
  section: RegenerateSection;
  instruction: string;
  at: number; // a new ask with the same text still reopens the form
}

export interface FlagActions {
  keep: (flag: Flag) => void;
  soften: (flag: Flag) => void;
  drop: (flag: Flag) => void;
  busy: boolean;
}

export const FlagActionsContext = createContext<FlagActions | null>(null);
export const RewriteAskContext = createContext<RewriteAsk | null>(null);

export function useFlagActions(): FlagActions | null {
  return useContext(FlagActionsContext);
}

export function useRewriteAsk(): RewriteAsk | null {
  return useContext(RewriteAskContext);
}
