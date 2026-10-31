import { ApiError } from "./client";

/** The backend's user-facing message for an API failure, or a fallback for anything else. */
export function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}
