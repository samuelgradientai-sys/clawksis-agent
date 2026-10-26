import { describe, expect, it } from "vitest";

import {
  DEFAULT_FILTERS,
  customPullTag,
  fmtBytes,
  fmtEta,
  hfRepoVisible,
  isFinalTransfer,
  mergeOllamaRows,
  ollamaModelVisible,
  type CookbookModel,
  type HFRepo,
} from "./cookbook";

const model = (over: Partial<CookbookModel>): CookbookModel => ({
  id: "m",
  name: "Qwen3 8B",
  family: "Qwen3",
  params_b: 8,
  ollama: "qwen3:8b",
  quant: "Q4_K_M",
  size_gb: 4.9,
  min_vram_gb: 6,
  min_ram_gb: 8,
  context: 40_960,
  tool_use: true,
  use_case: "General",
  fit: { mode: "cpu", tier: "good", reason: "" },
  installed: false,
  ...over,
});

const repo = (over: Partial<HFRepo>): HFRepo => ({
  repo: "acme/tiny-GGUF",
  author: "acme",
  name: "tiny-GGUF",
  downloads: 1,
  likes: 0,
  updated_at: "",
  license: "",
  gated: false,
  tags: [],
  context: 8192,
  architecture: "llama",
  params_b: 1,
  size_q4_gb: 1.6,
  tool_use: false,
  ...over,
});

describe("cookbook filters", () => {
  it("applies fit / tools / context / source the same way to Ollama models and GGUF repos", () => {
    const tooBig = model({ fit: { mode: "none", tier: "no_fit", reason: "" } });
    expect(ollamaModelVisible(tooBig, { ...DEFAULT_FILTERS, fit: "fits" })).toBe(false);
    expect(ollamaModelVisible(tooBig, { ...DEFAULT_FILTERS, fit: "no_fit" })).toBe(true);
    expect(ollamaModelVisible(model({}), { ...DEFAULT_FILTERS, ctx: 131072 })).toBe(false);
    expect(ollamaModelVisible(model({}), { ...DEFAULT_FILTERS, source: "gguf" })).toBe(false);

    expect(hfRepoVisible(repo({}), { ...DEFAULT_FILTERS, tools: "tools" }, 16)).toBe(false);
    expect(hfRepoVisible(repo({ size_q4_gb: 40 }), { ...DEFAULT_FILTERS, fit: "fits" }, 16)).toBe(false);
    // No GGUF metadata (size 0) is never ruled out by fit.
    expect(hfRepoVisible(repo({ size_q4_gb: 0 }), { ...DEFAULT_FILTERS, fit: "fits" }, 16)).toBe(true);
  });

  it("merges the local text match with live results it does not already hold", () => {
    const local = [model({ ollama: "qwen3:8b" }), model({ ollama: "llama3.1:8b", name: "Llama", family: "Llama" })];
    const remote = [model({ ollama: "qwen3:8b" }), model({ ollama: "qwen3:32b" })];
    expect(mergeOllamaRows(local, remote, "qwen").map((m) => m.ollama)).toEqual(["qwen3:8b", "qwen3:32b"]);
    expect(mergeOllamaRows(local, remote, "")).toBe(local);
  });

  it("offers a custom pull only for an unknown, tag-shaped query", () => {
    const models = [model({ ollama: "qwen3:8b" })];
    expect(customPullTag("phi4:14b", models)).toBe("phi4:14b");
    expect(customPullTag("QWEN3:8B", models)).toBeNull();
    expect(customPullTag("two words", models)).toBeNull();
  });
});

describe("cookbook formatting", () => {
  it("formats sizes and ETAs for progress rows", () => {
    expect(fmtBytes(0)).toBe("—");
    expect(fmtBytes(512 * 1024 ** 2)).toBe("512 MB");
    expect(fmtBytes(4.5 * 1024 ** 3)).toBe("4.5 GB");
    expect(fmtEta(75)).toBe("1m 15s");
    expect(fmtEta(3_700)).toBe("1h 1m");
  });

  it("knows when a transfer has stopped for good", () => {
    expect(isFinalTransfer("error: pulled but failed to run")).toBe(true);
    expect(isFinalTransfer("cancelled")).toBe(true);
    expect(isFinalTransfer("pulling")).toBe(false);
  });
});
