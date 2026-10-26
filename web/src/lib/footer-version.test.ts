import { describe, expect, it } from "vitest";
import type { StatusResponse } from "@/lib/api";
import { footerVersion } from "@/lib/footer-version";

const status = (fields: Record<string, unknown>) => fields as unknown as StatusResponse;

describe("footerVersion", () => {
  it("shows the release version", () => {
    expect(footerVersion(status({ version: "2026.7.20", display_version: "2026.7.20+3.abc1234" }))).toBe("v2026.7.20");
  });

  it("shows the commit instead of 'vunknown' for a checkout without release tags", () => {
    expect(footerVersion(status({ version: "unknown", display_version: "git.abc1234" }))).toBe("git.abc1234");
    expect(footerVersion(status({ version: "unknown", display_version: "unknown" }))).toBe("—");
    expect(footerVersion(status({ version: "unknown" }))).toBe("—");
    expect(footerVersion(null)).toBe("—");
  });
});
