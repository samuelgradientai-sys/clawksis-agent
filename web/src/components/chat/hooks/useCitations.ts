/**
 * useCitations — citar/referenciar mensajes previos del chat como contexto.
 *
 * Frontend puro (no toca el backend): el texto citado se antepone al prompt
 * como un bloque `> ...`, igual que useAttachments inyecta los archivos. Se
 * componen entre sí: buildPromptWithAttachments(buildPromptWithQuotes(text)).
 */

import { useCallback, useState } from "react";

export interface Citation {
  id: string;
  role: "user" | "assistant";
  excerpt: string;
}

const MAX_EXCERPT = 280;

interface UseCitationsResult {
  citations: Citation[];
  addCitation: (msg: { role: "user" | "assistant"; content: string }) => void;
  removeCitation: (id: string) => void;
  clear: () => void;
  buildPromptWithQuotes: (userText: string) => string;
}

export function useCitations(): UseCitationsResult {
  const [citations, setCitations] = useState<Citation[]>([]);

  const addCitation = useCallback(
    (msg: { role: "user" | "assistant"; content: string }) => {
      const raw = msg.content.replace(/\s+/g, " ").trim();
      if (!raw) return;
      const excerpt =
        raw.length > MAX_EXCERPT ? raw.slice(0, MAX_EXCERPT - 1) + "…" : raw;
      setCitations((prev) => {
        if (prev.some((c) => c.role === msg.role && c.excerpt === excerpt)) {
          return prev;
        }
        return [
          ...prev,
          {
            id:
              "cite-" +
              Date.now() +
              "-" +
              Math.random().toString(36).slice(2, 7),
            role: msg.role,
            excerpt,
          },
        ];
      });
    },
    [],
  );

  const removeCitation = useCallback((id: string) => {
    setCitations((prev) => prev.filter((c) => c.id !== id));
  }, []);

  const clear = useCallback(() => setCitations([]), []);

  const buildPromptWithQuotes = useCallback(
    (userText: string): string => {
      if (citations.length === 0) return userText;
      const blocks = citations.map((c) => {
        const who =
          c.role === "user" ? "mensaje del usuario" : "respuesta del asistente";
        return "Citando un " + who + " anterior:\n> " + c.excerpt;
      });
      return blocks.join("\n\n") + "\n\n" + userText;
    },
    [citations],
  );

  return { citations, addCitation, removeCitation, clear, buildPromptWithQuotes };
}
