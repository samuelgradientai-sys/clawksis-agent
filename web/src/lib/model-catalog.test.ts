import { describe, expect, it } from "vitest";
import type { ModelOptionProvider } from "@clawk/shared";

import type { AuxiliaryModelsResponse } from "./api-aux";
import {
  assignmentBaseUrl,
  buildModelCatalog,
  filterModelCatalog,
  MAIN_ROLE,
} from "./model-catalog";

function row(slug: string, extra: Partial<ModelOptionProvider> = {}): ModelOptionProvider {
  return { slug, name: slug, models: [], is_current: false, is_local: false, ...extra };
}

function aux(
  main: AuxiliaryModelsResponse["main"],
  tasks: Partial<AuxiliaryModelsResponse["tasks"][number]>[] = [],
): AuxiliaryModelsResponse {
  return {
    main,
    tasks: tasks.map((t) => ({ task: "", provider: "auto", model: "", base_url: "", ...t })),
  };
}

const VLLM = row("custom:vllm-box", {
  name: "vLLM box",
  models: ["qwen2.5-coder-7b", "llama-3.1-8b"],
  is_current: true,
  is_local: true,
  is_user_defined: true,
  api_url: "http://localhost:18080/v1",
  local_url: "http://localhost:18080/v1",
});
const OLLAMA = row("ollama", {
  name: "Ollama (local)",
  models: ["qwen2.5:7b", "llama3.2:3b"],
  is_local: true,
  local_url: "http://localhost:11434/v1",
});
const OPENROUTER = row("openrouter", { name: "OpenRouter", models: ["a/one", "b/two"] });
const ANTHROPIC = row("anthropic", { name: "Anthropic" });

describe("buildModelCatalog", () => {
  it("splits rows by the backend's locality verdict and keeps keyless providers apart", () => {
    // LM Studio's setup skeleton has a local default URL but nothing is configured there.
    const lmstudioSkeleton = row("lmstudio", {
      source: "canonical",
      is_local: true,
      local_url: "http://127.0.0.1:1234/v1",
    });
    const catalog = buildModelCatalog({
      options: { providers: [OPENROUTER, ANTHROPIC, OLLAMA, VLLM, lmstudioSkeleton] },
      aux: null,
      localStatus: null,
    });

    expect(catalog.local.map((p) => p.slug)).toEqual(["custom:vllm-box", "ollama"]);
    expect(catalog.cloud.map((p) => p.slug)).toEqual(["openrouter"]);
    expect(catalog.unconfigured.map((p) => p.slug)).toEqual(["anthropic", "lmstudio"]);
  });

  it("marks the main model on the endpoint row that serves a bare `custom` provider", () => {
    // config: provider: custom + base_url of the named endpoint. The row slug is
    // `custom:vllm-box`, so a slug comparison alone never finds the model in use.
    const catalog = buildModelCatalog({
      options: { providers: [OPENROUTER, OLLAMA, VLLM], model: "llama-3.1-8b", provider: "custom" },
      aux: aux({
        provider: "custom",
        model: "llama-3.1-8b",
        base_url: "http://localhost:18080/v1/",
        local_endpoint: true,
      }),
      localStatus: [],
    });

    const vllm = catalog.local.find((p) => p.slug === "custom:vllm-box");
    expect(vllm?.models[0]).toMatchObject({ id: "llama-3.1-8b", roles: [MAIN_ROLE] });
    expect(catalog.inUse).toEqual([
      expect.objectContaining({
        provider: "custom:vllm-box",
        model: "llama-3.1-8b",
        roles: [MAIN_ROLE],
        isLocal: true,
      }),
    ]);
    expect(catalog.local[0].slug).toBe("custom:vllm-box");
  });

  it("reports a local auxiliary pin whose server is down even when its row is gone", () => {
    // Ollama's picker row only exists while the daemon answers; the vision pin still routes there.
    const catalog = buildModelCatalog({
      options: { providers: [OPENROUTER] },
      aux: aux({ provider: "openrouter", model: "a/one" }, [
        {
          task: "vision",
          provider: "ollama",
          model: "qwen2.5:7b",
          base_url: "http://localhost:11434/v1",
          local_endpoint: true,
        },
      ]),
      localStatus: [{ url: "http://localhost:11434/v1", reachable: false, error: "ConnectError" }],
    });

    expect(catalog.inUse).toEqual([
      expect.objectContaining({ model: "a/one", roles: [MAIN_ROLE], isLocal: false }),
      expect.objectContaining({
        provider: "ollama",
        model: "qwen2.5:7b",
        roles: ["vision"],
        isLocal: true,
        reachability: "unreachable",
      }),
    ]);
  });

  it("merges the live model list into a local row: unserved and newly detected models", () => {
    const lmstudio = row("custom:lm-studio", {
      models: ["mistral-7b"],
      is_local: true,
      local_url: "http://localhost:1234/v1",
    });
    const catalog = buildModelCatalog({
      options: { providers: [lmstudio] },
      aux: null,
      localStatus: [
        { url: "http://localhost:1234/v1", reachable: true, models: ["phi-4", "gemma-3"] },
      ],
    });

    const [provider] = catalog.local;
    expect(provider.reachability).toBe("running");
    expect(provider.models).toEqual([
      { id: "mistral-7b", roles: [], served: false, detected: false },
      { id: "phi-4", roles: [], served: true, detected: true },
      { id: "gemma-3", roles: [], served: true, detected: true },
    ]);
  });

  it("distinguishes not-yet-probed, unreachable and start-on-demand local rows", () => {
    const llamacpp = row("llamacpp", { name: "Local", models: ["gemma"], is_local: true, source: "local-runtime" });
    const pending = buildModelCatalog({ options: { providers: [OLLAMA, llamacpp] }, aux: null, localStatus: null });
    expect(pending.local.map((p) => p.reachability)).toEqual(["checking", "on_demand"]);

    const probed = buildModelCatalog({
      options: { providers: [OLLAMA] },
      aux: null,
      localStatus: [{ url: "http://localhost:11434/v1/", reachable: false, error: "ConnectTimeout" }],
    });
    expect(probed.local[0]).toMatchObject({ reachability: "unreachable", probeError: "ConnectTimeout" });
  });

  it("groups slots sharing one model and pins in-use models first", () => {
    const catalog = buildModelCatalog({
      options: { providers: [OPENROUTER] },
      aux: aux({ provider: "openrouter", model: "b/two" }, [
        { task: "compression", provider: "openrouter", model: "b/two" },
        { task: "vision", provider: "auto", model: "ignored" },
      ]),
      localStatus: null,
    });

    expect(catalog.inUse).toHaveLength(1);
    expect(catalog.inUse[0].roles).toEqual([MAIN_ROLE, "compression"]);
    expect(catalog.cloud[0].models.map((m) => m.id)).toEqual(["b/two", "a/one"]);
  });
});

describe("filterModelCatalog", () => {
  const catalog = buildModelCatalog({
    options: { providers: [OPENROUTER, OLLAMA] },
    aux: null,
    localStatus: null,
  });

  it("keeps every model of a provider found by name", () => {
    const filtered = filterModelCatalog(catalog, "ollama");
    expect(filtered.local[0].models.map((m) => m.id)).toEqual(["qwen2.5:7b", "llama3.2:3b"]);
    expect(filtered.cloud).toEqual([]);
  });

  it("narrows to matching models otherwise", () => {
    const filtered = filterModelCatalog(catalog, "llama3");
    expect(filtered.local[0].models.map((m) => m.id)).toEqual(["llama3.2:3b"]);
  });
});

describe("assignmentBaseUrl", () => {
  it("routes custom endpoints and Ollama through their URL, never pins built-ins or llama.cpp", () => {
    expect(assignmentBaseUrl(VLLM)).toBe("http://localhost:18080/v1");
    expect(assignmentBaseUrl({ ...OLLAMA, source: "local" })).toBe("http://localhost:11434/v1");
    expect(
      assignmentBaseUrl({ source: "local-runtime", local_url: "http://127.0.0.1:39281/v1" }),
    ).toBe("");
    expect(assignmentBaseUrl(OPENROUTER)).toBe("");
  });
});
