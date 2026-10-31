import { api, getSessionToken, setSessionToken } from "./client";

export type SessionStatus = "ready" | "unauthorized";

/**
 * Establish the API session.
 *
 * The launcher opens `/?token=...`. The token is kept in memory only and removed from the
 * address bar so it isn't left in history or bookmarks. After a reload there's no token in the
 * URL, so it's recovered from GET /api/session (authorized by the HttpOnly cookie). Finally
 * POST /api/session refreshes that cookie, which EventSource needs because it can't send
 * headers.
 */
export async function bootstrapSession(
  location: Location = window.location,
  history: History = window.history,
): Promise<SessionStatus> {
  const url = new URL(location.href);
  const fromUrl = url.searchParams.get("token");
  if (fromUrl) {
    setSessionToken(fromUrl);
    url.searchParams.delete("token");
    history.replaceState(history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }

  if (!getSessionToken()) {
    const { data } = await api.GET("/api/session");
    if (data) setSessionToken(data.token);
  }
  if (!getSessionToken()) return "unauthorized";

  const { response } = await api.POST("/api/session");
  return response.ok ? "ready" : "unauthorized";
}
