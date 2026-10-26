import { describe, expect, it } from "vitest";
import { isStopPhrase, voiceSettingsFromConfig } from "./voiceSettings";

const defaults = { voice: { silence_duration: 3.0, stop_phrases: ["stop"], barge_in_grace_seconds: 0.5 } };

describe("voice settings from config.yaml", () => {
  it("keeps the conversation's own tuning while keys are at the backend defaults", () => {
    const settings = voiceSettingsFromConfig(defaults, defaults);
    expect(settings).toMatchObject({
      bargeIn: true,
      bargeInGraceMs: 500,
      silenceMs: 1_000,
      stopPhrases: { mode: "default" },
      chatMode: "chained",
    });
  });

  it("honours values the user changed", () => {
    const config = {
      voice: {
        silence_duration: 1.5,
        barge_in: false,
        barge_in_grace_seconds: 0.8,
        barge_in_threshold_multiplier: 2,
        stop_phrases: ["listo"],
        voice_chat_mode: "gpt_live",
      },
    };
    expect(voiceSettingsFromConfig(config, defaults)).toEqual({
      bargeIn: false,
      bargeInGraceMs: 800,
      bargeInMultiplier: 2,
      silenceMs: 1_500,
      stopPhrases: { mode: "custom", phrases: ["listo"] },
      chatMode: "gpt-live",
    });
    expect(voiceSettingsFromConfig({ voice: { stop_phrases: [] } }, defaults).stopPhrases).toEqual({ mode: "disabled" });
  });
});

describe("spoken stop phrases", () => {
  it("ends on a whole-utterance stop in Spanish or English, addressed or not", () => {
    for (const said of ["Basta.", "¡Chau!", "Clawk, terminar", "eso es todo", "Stop"]) {
      expect(isStopPhrase(said, { mode: "default" }), said).toBe(true);
    }
  });

  it("never swallows a real request that merely contains the word", () => {
    expect(isStopPhrase("pará el contenedor de docker", { mode: "default" })).toBe(false);
    expect(isStopPhrase("basta de errores en el build, revisalo", { mode: "default" })).toBe(false);
  });

  it("uses only the user's list when customised, and nothing when disabled", () => {
    expect(isStopPhrase("listo", { mode: "custom", phrases: ["Listo"] })).toBe(true);
    expect(isStopPhrase("basta", { mode: "custom", phrases: ["Listo"] })).toBe(false);
    expect(isStopPhrase("basta", { mode: "disabled" })).toBe(false);
  });
});
