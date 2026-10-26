import { describe, expect, it } from "vitest";
import { fill, todayCopy } from "./copy";

describe("todayCopy", () => {
  it("speaks Spanish to Spanish locales and English to the rest", () => {
    expect(todayCopy("es").emptyTodayTitle).toBe("Hoy todavía no hizo nada");
    expect(todayCopy("es-AR").pageTitle).toBe("Hoy");
    expect(todayCopy("fr").pageTitle).toBe("Today");
  });
});

describe("fill", () => {
  it("fills values and picks the word for each count", () => {
    const es = todayCopy("es");
    expect(fill(es.errorsCount, { count: 1 })).toBe("1 error");
    expect(fill(es.errorsCount, { count: 3 })).toBe("3 errores");
    expect(fill(es.statSkillsHint, { created: 1, updated: 0 })).toBe("1 nueva · 0 actualizadas");
    expect(fill("{a} y {b}", { a: "x" })).toBe("x y {b}");
  });
});
