/**
 * useAttachments — Hook para gestionar archivos adjuntos al composer.
 *
 * Fase 2.8 — B1 puro: solo archivos de texto, lectura en navegador.
 * NO requiere endpoints nuevos del backend. Los archivos se incluyen
 * inline en el prompt como bloques de código fenced.
 */

import { useCallback, useState } from "react";

export interface Attachment {
  id: string;
  name: string;
  size: number;
  content: string;
  extension: string;
}

const ALLOWED_EXTENSIONS = [
  "txt", "md", "markdown",
  "json", "yaml", "yml", "toml", "xml",
  "py", "ts", "tsx", "js", "jsx", "mjs", "cjs",
  "rs", "go", "java", "kt", "rb", "php", "swift",
  "c", "cpp", "h", "hpp", "cs",
  "sh", "bash", "zsh", "fish",
  "html", "css", "scss", "sass",
  "csv", "tsv",
  "sql",
  "env", "ini", "conf", "cfg",
  "log",
  "vue", "svelte",
  "graphql", "gql",
];

const MAX_FILE_SIZE = 100 * 1024;

interface UseAttachmentsResult {
  attachments: Attachment[];
  addFiles: (files: FileList | File[]) => Promise<void>;
  removeAttachment: (id: string) => void;
  clear: () => void;
  error: string | null;
  buildPromptWithAttachments: (userText: string) => string;
}

function getExtension(filename: string): string {
  const lastDot = filename.lastIndexOf(".");
  if (lastDot === -1) return "";
  return filename.slice(lastDot + 1).toLowerCase();
}

function isAcceptableFile(file: File): { ok: boolean; reason?: string } {
  if (file.size > MAX_FILE_SIZE) {
    const kb = Math.round(file.size / 1024);
    return {
      ok: false,
      reason: '"' + file.name + '" es muy grande (' + kb + 'KB). Máximo: 100KB.',
    };
  }
  const ext = getExtension(file.name);
  if (file.type.startsWith("text/")) return { ok: true };
  if (ext && ALLOWED_EXTENSIONS.includes(ext)) return { ok: true };
  if (file.type === "" && ext === "") {
    if (file.name.toLowerCase() === "dockerfile") return { ok: true };
  }
  return {
    ok: false,
    reason: '"' + file.name + '" no es un archivo de texto soportado.',
  };
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result === "string") {
        resolve(result);
      } else {
        reject(new Error("Failed to read file as text"));
      }
    };
    reader.onerror = () => reject(reader.error ?? new Error("FileReader error"));
    reader.readAsText(file, "utf-8");
  });
}

export function useAttachments(): UseAttachmentsResult {
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [error, setError] = useState<string | null>(null);

  const addFiles = useCallback(async (files: FileList | File[]) => {
    setError(null);
    const filesArray = Array.from(files);
    const newAttachments: Attachment[] = [];
    const errors: string[] = [];

    for (const file of filesArray) {
      const check = isAcceptableFile(file);
      if (!check.ok) {
        errors.push(check.reason!);
        continue;
      }
      try {
        const content = await readFileAsText(file);
        newAttachments.push({
          id: "att-" + Date.now() + "-" + Math.random().toString(36).slice(2, 9),
          name: file.name,
          size: file.size,
          content,
          extension: getExtension(file.name),
        });
      } catch (err) {
        errors.push(
          '"' + file.name + '": ' + (err instanceof Error ? err.message : "error al leer"),
        );
      }
    }

    if (newAttachments.length > 0) {
      setAttachments((prev) => [...prev, ...newAttachments]);
    }
    if (errors.length > 0) {
      setError(errors.join(" · "));
    }
  }, []);

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const clear = useCallback(() => {
    setAttachments([]);
    setError(null);
  }, []);

  const buildPromptWithAttachments = useCallback(
    (userText: string): string => {
      if (attachments.length === 0) return userText;
      const blocks = attachments.map((att) => {
        const lang = att.extension || "";
        return "\n\n--- Archivo adjunto: " + att.name + " ---\n```" + lang + "\n" + att.content + "\n```";
      });
      return userText + blocks.join("");
    },
    [attachments],
  );

  return {
    attachments,
    addFiles,
    removeAttachment,
    clear,
    error,
    buildPromptWithAttachments,
  };
}
