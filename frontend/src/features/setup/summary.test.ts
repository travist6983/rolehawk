import { describe, expect, it } from "vitest";

import { summarizeApply } from "./summary";

describe("summarizeApply", () => {
  it("uses friendly, correctly pluralized nouns", () => {
    expect(
      summarizeApply({ added: { experience: 2, education: 1, skills: 3, certifications: 1 } }),
    ).toBe("Added 2 roles, 1 school, 3 skills, 1 certification");
    expect(summarizeApply({ added: {} })).toBe("Profile updated");
  });
});
