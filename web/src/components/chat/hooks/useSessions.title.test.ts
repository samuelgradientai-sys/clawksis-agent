import { describe, expect, it } from "vitest";
import { deriveTitle, sanitizeSessionLabel } from "./useSessions";

describe("session titles", () => {
  it("drop markdown marks a model left in the title", () => {
    expect(sanitizeSessionLabel("¡Hola! Soy el **modelo de prueba**")).toBe("¡Hola! Soy el modelo de prueba");
    expect(sanitizeSessionLabel("## Revisar `config.yaml` y *logs*")).toBe("Revisar config.yaml y logs");
  });

  it("keep identifiers with underscores and plain asterisks", () => {
    expect(sanitizeSessionLabel("Fix __init__ in snake_case_module")).toBe("Fix __init__ in snake_case_module");
    expect(sanitizeSessionLabel("5 * 3 * 2")).toBe("5 * 3 * 2");
  });

  it("fall back to the preview when the title is empty", () => {
    expect(deriveTitle({ id: "abc", title: "", preview: "Plan **de** viaje" } as never)).toBe("Plan de viaje");
  });
});
