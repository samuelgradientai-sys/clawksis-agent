import { describe, expect, it } from "vitest";

import type { ModelOptionProvider } from "./hooks/useModelOptions";
import { groupMenuModels } from "./model-menu-groups";

const ROWS: ModelOptionProvider[] = [
  { slug: "openrouter", name: "OpenRouter", models: ["anthropic/x", "qwen/qwen3"] },
  {
    slug: "custom:vllm-box",
    name: "vLLM box",
    models: ["qwen2.5-coder-7b", "llama-3.1-8b"],
    is_current: true,
    is_local: true,
  },
  { slug: "ollama", name: "Ollama (local)", models: ["qwen2.5:7b"], is_local: true },
];

describe("groupMenuModels", () => {
  it("pins the live session's model even when its provider slug differs from the session's", () => {
    // session.info / model.options report provider "custom"; the row is custom:vllm-box.
    const groups = groupMenuModels(ROWS, "llama-3.1-8b", "custom", "");

    expect(groups.inUse).toEqual({
      provider: "custom:vllm-box",
      providerName: "vLLM box",
      model: "llama-3.1-8b",
      isLocal: true,
    });
  });

  it("lists local providers apart from cloud ones, in the backend's order", () => {
    const groups = groupMenuModels(ROWS, "", "", "");

    expect(groups.local.map((g) => g.slug)).toEqual(["custom:vllm-box", "ollama"]);
    expect(groups.cloud.map((g) => g.slug)).toEqual(["openrouter"]);
  });

  it("filters models but keeps every model of a provider found by name", () => {
    expect(groupMenuModels(ROWS, "", "", "qwen").cloud[0].models).toEqual(["qwen/qwen3"]);
    expect(groupMenuModels(ROWS, "", "", "ollama").local).toEqual([
      { slug: "ollama", name: "Ollama (local)", isLocal: true, models: ["qwen2.5:7b"] },
    ]);
  });

  it("does not mark a same-named model on another provider as in use", () => {
    const rows: ModelOptionProvider[] = [
      { slug: "openrouter", name: "OpenRouter", models: ["llama-3.1-8b"] },
      { slug: "ollama", name: "Ollama", models: ["llama-3.1-8b"], is_current: true, is_local: true },
    ];
    expect(groupMenuModels(rows, "llama-3.1-8b", "ollama", "").inUse?.provider).toBe("ollama");
  });
});
