/**
 * Typed API client. Types come from the backend's OpenAPI schema (`npm run gen:api` from the
 * repo root regenerates them), so a backend change that breaks the frontend fails `tsc`.
 */
import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export const TOKEN_HEADER = "X-Offerbound-Token";

let sessionToken: string | null = null;
const unauthorizedListeners = new Set<() => void>();

export function getSessionToken(): string | null {
  return sessionToken;
}

export function setSessionToken(token: string | null): void {
  sessionToken = token;
}

/** Called when the API rejects the session (the app was restarted with a new token). */
export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

const auth: Middleware = {
  onRequest({ request }) {
    if (sessionToken) request.headers.set(TOKEN_HEADER, sessionToken);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401)
      unauthorizedListeners.forEach((listener) => {
        listener();
      });
    return response;
  },
};

export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  // Resolve fetch per request (not at import) so wrappers installed later, such as test mocks,
  // still apply.
  fetch: (request: Request) => globalThis.fetch(request),
});
api.use(auth);

/** An API failure with the backend's user-facing message. */
export class ApiError extends Error {
  readonly status: number;
  readonly kind: string | undefined;

  constructor(status: number, message: string, kind?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
  }
}

function messageFrom(error: unknown, status: number): { message: string; kind?: string } {
  if (error && typeof error === "object" && "detail" in error) {
    const { detail, kind } = error as { detail: unknown; kind?: unknown };
    const kindText = typeof kind === "string" ? kind : undefined;
    if (typeof detail === "string") return { message: detail, kind: kindText };
    if (Array.isArray(detail) && detail.length > 0) {
      const first: unknown = detail[0];
      if (first && typeof first === "object" && "msg" in first) {
        return { message: String(first.msg), kind: kindText };
      }
    }
  }
  return { message: `Request failed (${String(status)})` };
}

interface ApiResult {
  data?: unknown;
  error?: unknown;
  response: Response;
}

/** Await an openapi-fetch call and return its data, or throw ApiError. */
export async function unwrap<R extends ApiResult>(
  call: Promise<R>,
): Promise<NonNullable<R["data"]>> {
  const result = await call;
  if (result.error !== undefined || !result.response.ok || result.data == null) {
    const { message, kind } = messageFrom(result.error, result.response.status);
    throw new ApiError(result.response.status, message, kind);
  }
  return result.data;
}
