import { describe, expect, it } from "vitest";

import { coverage, displayName, parseCompanyList, plural, timeAgo } from "./sourceText";

describe("parseCompanyList", () => {
  it("reads board links for every ATS and bare names with the fallback", () => {
    const text = [
      "https://boards.greenhouse.io/stripe",
      "job-boards.greenhouse.io/figma/jobs/123",
      "https://boards-api.greenhouse.io/v1/boards/airbnb/jobs",
      "https://jobs.lever.co/plaid?team=eng",
      "jobs.eu.lever.co/mistral",
      "https://jobs.ashbyhq.com/ramp/abc-123",
      "https://apply.workable.com/workmotion/",
      "acme.workable.com",
      "notion, linear",
    ].join("\n");
    expect(parseCompanyList(text, "ashby")).toEqual({
      entries: [
        { ats: "greenhouse", slug: "stripe" },
        { ats: "greenhouse", slug: "figma" },
        { ats: "greenhouse", slug: "airbnb" },
        { ats: "lever", slug: "plaid" },
        { ats: "lever", slug: "mistral" },
        { ats: "ashby", slug: "ramp" },
        { ats: "workable", slug: "workmotion" },
        { ats: "workable", slug: "acme" },
        { ats: "ashby", slug: "notion" },
        { ats: "ashby", slug: "linear" },
      ],
      invalid: [],
    });
  });

  it("drops duplicates and CSV headers, and reports what it can't read", () => {
    const parsed = parseCompanyList(
      'slug\n"stripe"\nStripe\nhttps://example.com/careers\nboards.greenhouse.io/\n-bad',
      "greenhouse",
    );
    expect(parsed.entries).toEqual([{ ats: "greenhouse", slug: "stripe" }]);
    expect(parsed.invalid).toEqual([
      "https://example.com/careers",
      "boards.greenhouse.io/",
      "-bad",
    ]);
  });

  it("keeps the same slug on different boards apart", () => {
    const parsed = parseCompanyList("acme\njobs.lever.co/acme", "greenhouse");
    expect(parsed.entries).toHaveLength(2);
  });
});

describe("display helpers", () => {
  it("turns slugs into names", () => {
    expect(displayName("acme-corp_io")).toBe("Acme Corp Io");
  });

  it("says how long ago", () => {
    const now = new Date("2026-10-31T12:00:00Z");
    expect(timeAgo("2026-10-31T11:59:50Z", now)).toBe("just now");
    expect(timeAgo("2026-10-31T11:55:00Z", now)).toBe("5 minutes ago");
    expect(timeAgo("2026-10-31T09:00:00Z", now)).toBe("3 hours ago");
    expect(timeAgo("2026-10-30T12:00:00Z", now)).toBe("yesterday");
  });

  it("describes coverage and counts", () => {
    expect(coverage(["*"])).toBeNull();
    expect(coverage(["US"])).toBe("US only");
    expect(coverage(["GB", "US"])).toBe("2 countries");
    expect(plural(1, "company", "companies")).toBe("1 company");
    expect(plural(1200, "job")).toBe("1,200 jobs");
  });
});
