import { describe, expect, it } from "vitest";

import { ollamaAvailable, ollamaStatusText } from "./cookbook-ollama";

describe("ollama availability", () => {
  it("counts a reachable daemon without a local binary as available (Ollama in a container)", () => {
    const external = { installed: false, running: true, models: ["qwen2.5:7b"] };
    expect(ollamaAvailable(external)).toBe(true);
    expect(ollamaStatusText(external, "")).toBe("Running (external daemon) · 1 model(s) pulled");
  });

  it("is unavailable only when there is neither a binary nor a daemon", () => {
    expect(ollamaAvailable({ installed: false, running: false })).toBe(false);
    expect(ollamaStatusText({ installed: false, running: false }, "")).toBe("Not installed.");
    expect(ollamaStatusText({ installed: true, running: false }, "")).toContain("Installed");
  });
});
