import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";

import { getSessionToken, TOKEN_HEADER } from "./client";
import { bootstrapSession } from "./session";

function fakeLocation(href: string): Location {
  return { href } as Location;
}

function fakeHistory() {
  const calls: string[] = [];
  const history = {
    state: null,
    replaceState: (_state: unknown, _title: string, url: string) => {
      calls.push(url);
    },
  } as unknown as History;
  return { history, calls };
}

describe("bootstrapSession", () => {
  it("takes the token from the launch URL, removes it, and sets the cookie", async () => {
    let cookieHeader: string | null = null;
    server.use(
      http.get("/api/session", () =>
        HttpResponse.json({ detail: "should not be called" }, { status: 500 }),
      ),
      http.post("/api/session", ({ request }) => {
        cookieHeader = request.headers.get(TOKEN_HEADER);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { history, calls } = fakeHistory();
    const status = await bootstrapSession(
      fakeLocation("http://localhost:3000/settings?token=abc123&x=1#top"),
      history,
    );

    expect(status).toBe("ready");
    expect(getSessionToken()).toBe("abc123");
    expect(calls).toEqual(["/settings?x=1#top"]);
    expect(cookieHeader).toBe("abc123");
  });

  it("recovers the token from the cookie-authenticated session after a reload", async () => {
    const { history, calls } = fakeHistory();
    const status = await bootstrapSession(fakeLocation("http://localhost:3000/"), history);
    expect(status).toBe("ready");
    expect(getSessionToken()).toBe("test-token");
    expect(calls).toEqual([]);
  });

  it("reports unauthorized when there is no token anywhere", async () => {
    server.use(
      http.get("/api/session", () => HttpResponse.json({ detail: "no" }, { status: 401 })),
    );
    const { history } = fakeHistory();
    expect(await bootstrapSession(fakeLocation("http://localhost:3000/"), history)).toBe(
      "unauthorized",
    );
  });
});
