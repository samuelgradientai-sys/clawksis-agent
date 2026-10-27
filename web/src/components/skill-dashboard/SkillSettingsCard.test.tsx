// @vitest-environment jsdom
// The settings card edits what a skill declares in `metadata.clawk.config`:
// labels follow the locale, only changed values are sent, and a change the
// backend marks as risky is saved only after the user confirms it.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { en } from "@/i18n/en";
import { es } from "@/i18n/es";
import type { SkillDashboardsCopy } from "@/i18n/types";
import type { SaveResult, SkillSettingField } from "@/lib/api-skill-settings";
import { SkillSettingsCard } from "./SkillSettingsCard";

const get = vi.fn<(name: string) => Promise<{ name: string; fields: SkillSettingField[] }>>();
const save = vi.fn<(name: string, values: Record<string, unknown>, confirm?: boolean) => Promise<SaveResult>>();
vi.mock("@/lib/api-skill-settings", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-skill-settings")>()),
  skillSettingsApi: {
    get: (name: string) => get(name),
    save: (name: string, values: Record<string, unknown>, confirm?: boolean) => save(name, values, confirm),
  },
}));

const FIELDS: SkillSettingField[] = [
  {
    key: "kronos.trading.enabled",
    description: "Let the agent place eToro orders",
    default: false,
    type: "bool",
    label: { es: "Trading automático" },
    confirm: true,
    value: false,
    is_set: false,
  },
  {
    key: "kronos.goals.risk",
    description: "Risk tolerance",
    default: "low",
    type: "choice",
    choices: ["low", "medium", "high"],
    choice_labels: { es: { low: "Bajo", medium: "Medio", high: "Alto" } },
    label: { es: "Riesgo" },
    value: "low",
    is_set: false,
  },
  {
    key: "kronos.trading.max_order_usd",
    description: "Max USD per buy",
    default: 100,
    type: "integer",
    min: 1,
    confirm: true,
    label: { es: "Máximo por orden (USD)" },
    value: 2000,
    is_set: true,
  },
];

const copy = { ...en.skillDashboards, ...es.skillDashboards } as SkillDashboardsCopy;
let container: HTMLDivElement;
let root: Root;
const onSaved = vi.fn();

async function render() {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<SkillSettingsCard copy={copy} locale="es" name="kronos" onSaved={onSaved} />));
}

function button(text: string): HTMLButtonElement {
  const found = [...document.querySelectorAll("button")].find((b) => b.textContent?.trim() === text);
  if (!found) throw new Error(`no button "${text}"`);
  return found as HTMLButtonElement;
}

function setInput(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  setter.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

beforeEach(() => {
  get.mockReset().mockResolvedValue({ name: "kronos", fields: FIELDS });
  save.mockReset();
  onSaved.mockReset();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
});

describe("SkillSettingsCard", () => {
  it("shows the skill's settings in the user's language", async () => {
    await render();
    const text = container.textContent ?? "";
    expect(text).toContain("Trading automático");
    expect(text).toContain("Máximo por orden (USD)");
    expect(text).toContain("Riesgo");
    expect(text).toContain("pide confirmación");
    expect(button("Guardar cambios").disabled).toBe(true);
  });

  it("asks before saving a risky change, then saves only what changed", async () => {
    await render();
    const limit = container.querySelector<HTMLInputElement>("#skill-setting-kronos-trading-max_order_usd")!;
    await act(async () => setInput(limit, "5000"));

    save.mockResolvedValueOnce({ ok: false, needsConfirmation: ["kronos.trading.max_order_usd"] });
    await act(async () => button("Guardar cambios").click());
    expect(save).toHaveBeenLastCalledWith("kronos", { "kronos.trading.max_order_usd": "5000" }, false);
    expect(document.body.textContent).toContain("Máximo por orden (USD) → 5000");
    expect(onSaved).not.toHaveBeenCalled();

    const saved = FIELDS.map((f) => (f.key === "kronos.trading.max_order_usd" ? { ...f, value: 5000 } : f));
    save.mockResolvedValueOnce({ ok: true, changed: ["kronos.trading.max_order_usd"], fields: saved });
    await act(async () => button("Sí, guardar").click());
    expect(save).toHaveBeenLastCalledWith("kronos", { "kronos.trading.max_order_usd": "5000" }, true);
    expect(onSaved).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("Ajustes guardados");
  });

  it("cancelling the confirmation saves nothing", async () => {
    await render();
    const limit = container.querySelector<HTMLInputElement>("#skill-setting-kronos-trading-max_order_usd")!;
    await act(async () => setInput(limit, "9000"));
    save.mockResolvedValueOnce({ ok: false, needsConfirmation: ["kronos.trading.max_order_usd"] });
    await act(async () => button("Guardar cambios").click());
    await act(async () => button("Cancelar").click());
    expect(save).toHaveBeenCalledOnce();
    expect(onSaved).not.toHaveBeenCalled();
  });
});
