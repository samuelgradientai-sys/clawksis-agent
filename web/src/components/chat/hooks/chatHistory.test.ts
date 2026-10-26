import { describe, expect, it } from "vitest";
import { contentToText, mapHistoryMessages } from "./chatHistory";
import { lastUserIsSlash } from "./chatTranscript";

describe("stored transcript rows become string bubbles", () => {
  it("flattens a REST image turn (OpenAI parts array) into text plus a preview", () => {
    const rest = [
      {
        id: 41,
        role: "user",
        content: [
          { type: "text", text: "mira esto" },
          { type: "image_url", image_url: { url: "data:image/png;base64,AAAA" } },
        ],
      },
      { id: 42, role: "assistant", content: "Es un gato." },
    ];
    const msgs = mapHistoryMessages(rest, "h");
    expect(msgs.map((m) => m.content)).toEqual(["mira esto", "Es un gato."]);
    expect(msgs[0].images).toEqual([{ previewUrl: "data:image/png;base64,AAAA", name: "imagen adjunta" }]);
    expect(msgs.map((m) => m.rowId)).toEqual([41, 42]);
    // The composer and the bubbles call string methods on the last user turn.
    expect(lastUserIsSlash(msgs)).toBe(false);
  });

  it("turns native-vision @image refs into previews and keeps the caption", () => {
    const [msg] = mapHistoryMessages(
      [{ role: "user", text: "¿qué ves?\n\n@image:/home/u/pics/cat.png\n@image:`/tmp/with space.jpg`", row_id: 7 }],
      "h",
    );
    expect(msg.content).toBe("¿qué ves?");
    expect(msg.images?.map((i) => i.name)).toEqual(["cat.png", "with space.jpg"]);
    expect(msg.images?.[1].previewUrl).toBe("/media/local?path=" + encodeURIComponent("/tmp/with space.jpg"));
    expect(msg.rowId).toBe(7);
  });

  it("hides system-note rows but keeps skill invocations and steers", () => {
    const msgs = mapHistoryMessages(
      [
        { role: "user", text: "[System note: Your previous turn was interrupted mid-run …]", display_kind: "auto_continue" },
        { role: "user", text: "[System: stream timed out, continue]" },
        { role: "user", text: "/resumen hoy", display_kind: "skill_invocation" },
        { role: "user", text: "más corto", display_kind: "steer" },
        { role: "assistant", text: "Listo." },
      ],
      "h",
    );
    expect(msgs.map((m) => m.content)).toEqual(["/resumen hoy", "más corto", "Listo."]);
  });

  it("keeps tool args, from the gateway projection or the REST assistant tool_calls", () => {
    const gateway = mapHistoryMessages(
      [
        { role: "user", text: "lista" },
        { role: "tool", name: "terminal", args: { command: "ls -la" }, context: "ls -la" },
        { role: "assistant", text: "Hecho." },
      ],
      "g",
    );
    expect(gateway[1].toolCalls[0]).toMatchObject({ name: "terminal", args: { command: "ls -la" }, summary: "ls -la" });

    const rest = mapHistoryMessages(
      [
        { role: "user", content: "lista" },
        {
          role: "assistant",
          content: null,
          tool_calls: [{ id: "c1", function: { name: "terminal", arguments: '{"command":"pwd"}' } }],
        },
        { role: "tool", tool_call_id: "c1", content: "/root" },
        { role: "assistant", content: "Estás en /root." },
      ],
      "r",
    );
    expect(rest.map((m) => m.content)).toEqual(["lista", "Estás en /root."]);
    expect(rest[1].toolCalls[0]).toMatchObject({ name: "terminal", args: { command: "pwd" } });
  });

  it("reads stored Unix-second timestamps as milliseconds", () => {
    const [msg] = mapHistoryMessages([{ role: "user", text: "hola", timestamp: 1_700_000_000 }], "h");
    expect(msg.timestamp).toBe(1_700_000_000_000);
  });

  it("contentToText accepts strings, parts and single part objects", () => {
    expect(contentToText("plain").text).toBe("plain");
    expect(contentToText({ type: "text", text: "uno" }).text).toBe("uno");
    expect(contentToText(null)).toEqual({ text: "", images: [] });
  });
});
