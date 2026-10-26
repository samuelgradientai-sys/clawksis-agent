import { describe, expect, it } from "vitest";

import { sessionInfoProvider } from "./session-info-model";

describe("sessionInfoProvider", () => {
  it("reads the provider key the gateway's session.info actually sends", () => {
    expect(
      sessionInfoProvider({ model: "qwen2.5:7b", provider: "ollama", reasoning_effort: "" }),
    ).toBe("ollama");
  });

  it("keeps the previous value when the payload carries no provider", () => {
    expect(sessionInfoProvider({ model: "x", provider: "" })).toBeUndefined();
    expect(sessionInfoProvider({ title: "only a title" })).toBeUndefined();
    expect(sessionInfoProvider(null)).toBeUndefined();
  });
});
