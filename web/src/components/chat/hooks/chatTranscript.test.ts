import { describe, expect, it } from "vitest";
import {
  assistantBubble,
  completeTurn,
  editResubmitParams,
  matchUserRowId,
  userBubble,
  withStreamingBubble,
} from "./chatTranscript";
import type { ChatMessage } from "./useChatGateway";

const streamingTurn = (): ChatMessage[] => withStreamingBubble([userBubble("hola", { rowId: 1 })]);

describe("message.complete settles the reply", () => {
  it("shows a failed turn's account when nothing streamed", () => {
    const out = completeTurn(streamingTurn(), "", {
      status: "error",
      text: "Authentication failed\nDetails: invalid api key",
      error: "invalid api key",
    });
    expect(out[out.length - 1]).toMatchObject({
      role: "assistant",
      streaming: false,
      content: "Authentication failed\nDetails: invalid api key",
    });
  });

  it("falls back to the error when a failed turn has no text either", () => {
    const out = completeTurn(streamingTurn(), "", { status: "error", text: "", error: "credit balance too low" });
    expect(out[out.length - 1].content).toBe("credit balance too low");
  });

  it("keeps a non-streaming provider's whole reply", () => {
    const out = completeTurn(streamingTurn(), "", { status: "complete", text: "Respuesta completa" });
    expect(out[out.length - 1].content).toBe("Respuesta completa");
  });

  it("prefers the streamed text, unless the backend transformed the final", () => {
    const streamed = completeTurn(streamingTurn(), "Hola mundo", { text: "mundo" });
    expect(streamed[streamed.length - 1].content).toBe("Hola mundo");
    const transformed = completeTurn(streamingTurn(), "borrador", { text: "versión final", response_transformed: true });
    expect(transformed[transformed.length - 1].content).toBe("versión final");
  });

  it("creates the final message when the turn finished out of view", () => {
    const out = completeTurn([userBubble("hola")], "", { text: "tarde pero llega" });
    expect(out.map((m) => m.content)).toEqual(["hola", "tarde pero llega"]);
  });

  it("binds the durable rows the turn wrote", () => {
    const out = completeTurn(withStreamingBubble([userBubble("sin fila")]), "ok", {
      text: "ok",
      persisted_turn: { row_ids: [10, 11], complete: true, user_row_id: 10, final_assistant_row_id: 11 },
    });
    expect(out.map((m) => m.rowId)).toEqual([10, 11]);
  });
});

describe("edit & resubmit consent", () => {
  const view = (): ChatMessage[] => [
    userBubble("primero", { rowId: 5 }),
    assistantBubble({ content: "r1", streaming: false, rowId: 6 }),
    userBubble("/status"),
    assistantBubble({ id: "slash-1", content: "status", streaming: false }),
    userBubble("segundo", { rowId: 7 }),
    assistantBubble({ content: "r2", streaming: false, rowId: 8 }),
  ];

  it("aims the cut by row id with confirm_truncate", () => {
    const msgs = view();
    const plan = editResubmitParams(msgs, msgs[4].id, "segundo editado");
    expect(plan).toEqual({
      index: 4,
      params: { text: "segundo editado", truncate_before_row_id: 7, confirm_truncate: true },
    });
  });

  it("asks for the empty-transcript and deep-cut consents when editing the first turn", () => {
    const msgs = view();
    expect(editResubmitParams(msgs, msgs[0].id, "otro")?.params).toEqual({
      text: "otro",
      truncate_before_row_id: 5,
      confirm_truncate: true,
      confirm_empty_truncate: true,
      confirm_deep_truncate: true,
    });
  });

  it("refuses a bubble with no durable row", () => {
    const msgs = [userBubble("sin fila")];
    expect(editResubmitParams(msgs, msgs[0].id, "x")).toBeNull();
  });

  it("finds a bubble's row in a fresh transcript by text and occurrence", () => {
    const local = [userBubble("hola"), assistantBubble({ content: "a" }), userBubble("hola")];
    const fresh = [userBubble("hola", { rowId: 1 }), userBubble("hola", { rowId: 3 })];
    expect(matchUserRowId(local, 2, fresh)).toBe(3);
  });
});
