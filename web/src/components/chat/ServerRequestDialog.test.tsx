// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ServerRequestDialog } from "./ServerRequestDialog";
import { parseServerRequest, type ChatServerRequest } from "./hooks/serverRequests";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
const onAnswer = vi.fn();

function show(requests: ChatServerRequest[]) {
  act(() => root.render(<ServerRequestDialog requests={requests} liveSessionId="live-1" onAnswer={onAnswer} />));
}

const press = (label: string) =>
  act(() => {
    [...document.querySelectorAll("button")].find((b) => b.textContent === label)!.click();
  });

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  onAnswer.mockReset();
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("answers the agent's questions with the shapes the gateway reads", () => {
  it("approval → {choice}", () => {
    const req = parseServerRequest("srq-1", "approval", { session_id: "live-1", command: "rm -rf /x", choices: ["once", "session", "deny"] })!;
    show([req]);
    expect(document.body.textContent).toContain("rm -rf /x");
    expect(document.body.textContent).not.toContain("Permitir siempre");
    press("Permitir en esta sesión");
    expect(onAnswer).toHaveBeenCalledWith(req, { choice: "session" });
    press("Denegar");
    expect(onAnswer).toHaveBeenLastCalledWith(req, { choice: "deny" });
  });

  it("clarify → {answers}; a multi-select answer is a JSON array; Omitir cancels with {}", () => {
    const req = parseServerRequest("srq-2", "clarify", {
      session_id: "live-1",
      questions: [
        { qid: "q1", question: "¿Color?", choices: ["rojo", "azul"] },
        { qid: "q2", question: "¿Días?", choices: ["lun", "mar", "mié"], multi_select: true },
      ],
    })!;
    show([req]);
    press("azul");
    press("lun");
    press("mié");
    press("Responder");
    expect(onAnswer).toHaveBeenCalledWith(req, { answers: { q1: "azul", q2: '["lun","mié"]' } });
    press("Omitir");
    expect(onAnswer).toHaveBeenLastCalledWith(req, {});
  });

  it("sudo → {value}; skipping answers ''", () => {
    const req = parseServerRequest("srq-3", "sudo", { session_id: "other", command: "sudo apt update" })!;
    show([req]);
    expect(document.body.textContent).toContain("En otra conversación");
    press("Omitir");
    expect(onAnswer).toHaveBeenCalledWith(req, { value: "" });
  });

  it("shows one request at a time, oldest first", () => {
    const a = parseServerRequest("srq-4", "secret", { session_id: "live-1", env_var: "API_KEY", prompt: "Pega la clave" })!;
    const b = parseServerRequest("srq-5", "approval", { session_id: "live-1" })!;
    show([a, b]);
    expect(document.body.textContent).toContain("Pega la clave");
    expect(document.body.textContent).toContain("1 de 2");
    expect(document.body.textContent).not.toContain("Aprobación requerida");
  });
});
