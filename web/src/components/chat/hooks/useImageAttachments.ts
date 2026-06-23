/**
 * useImageAttachments — adjuntar imágenes (pegar / arrastrar) al chat moderno.
 *
 * Las imágenes no se pueden embeber como texto (a diferencia de useAttachments),
 * así que el flujo es: subir la imagen al server (api.uploadFile → data URL a un
 * path gestionado) y luego stagearla en la sesión vía el RPC `image.attach`
 * (por path absoluto). El siguiente prompt.submit incluye las imágenes adjuntas.
 * Quitar una usa `image.detach`. Requiere un modelo con visión.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { RpcSender } from "./useSessions";

export interface ImageAttachment {
  id: string;
  name: string;
  /** data URL para el thumbnail local. */
  previewUrl: string;
  /** path absoluto en el server (lo que conoce image.attach/detach). */
  serverPath: string;
}

const MAX_IMAGE_BYTES = 12 * 1024 * 1024; // 12MB

interface UseImageAttachmentsResult {
  images: ImageAttachment[];
  addImage: (file: File) => Promise<void>;
  removeImage: (id: string) => void;
  clear: () => void;
  uploading: boolean;
  error: string | null;
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = () => reject(r.error ?? new Error("FileReader error"));
    r.readAsDataURL(blob);
  });
}

function sanitizeName(name: string): string {
  const cleaned = (name || "image.png").replace(/[^a-zA-Z0-9._-]/g, "_");
  return cleaned.slice(0, 80) || "image.png";
}

export function useImageAttachments(
  sendRpc: RpcSender,
  sessionId: string | null,
): UseImageAttachmentsResult {
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Al cambiar de sesión: limpiar los chips (no son de la nueva conversación) y
  // hacer best-effort detach contra la sesión VIEJA (removeImage/clear cierran
  // sobre el sessionId nuevo, así que sin esto el detach iría a la sesión
  // equivocada y la imagen quedaría huérfana en la sesión anterior).
  const prevSidRef = useRef<string | null>(sessionId);
  useEffect(() => {
    if (prevSidRef.current === sessionId) return;
    const oldSid = prevSidRef.current;
    prevSidRef.current = sessionId;
    setImages((prev) => {
      if (oldSid) {
        for (const img of prev) {
          void sendRpc("image.detach", {
            session_id: oldSid,
            path: img.serverPath,
          }).catch(() => {});
        }
      }
      return [];
    });
    setError(null);
  }, [sessionId, sendRpc]);

  const addImage = useCallback(
    async (file: File): Promise<void> => {
      if (!sessionId) {
        setError("No hay sesión activa todavía");
        return;
      }
      if (!file.type.startsWith("image/")) {
        setError(`"${file.name}" no es una imagen`);
        return;
      }
      if (file.size > MAX_IMAGE_BYTES) {
        setError(
          `"${file.name}" es muy grande (${Math.round(file.size / 1024 / 1024)}MB). Máximo 12MB.`,
        );
        return;
      }
      setError(null);
      setUploading(true);
      try {
        const dataUrl = await blobToDataUrl(file);
        const uploadPath = `chat-uploads/${Date.now()}_${sanitizeName(file.name)}`;
        const res = await api.uploadFile(uploadPath, dataUrl, true);
        // image.attach resuelve por path absoluto. uploadFile devuelve el root
        // gestionado (absoluto) + el path relativo guardado.
        const root = (res.root || "").replace(/[\\/]+$/, "");
        const absPath = root ? `${root}/${res.path}` : res.path;
        await sendRpc("image.attach", { session_id: sessionId, path: absPath });
        setImages((prev) => [
          ...prev,
          {
            id: "img-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7),
            name: file.name,
            previewUrl: dataUrl,
            serverPath: absPath,
          },
        ]);
      } catch (err) {
        console.error("[useImageAttachments] addImage failed", err);
        setError(
          err instanceof Error
            ? err.message.replace(/^\d+:\s*/, "")
            : "No se pudo adjuntar la imagen",
        );
      } finally {
        setUploading(false);
      }
    },
    [sendRpc, sessionId],
  );

  const removeImage = useCallback(
    (id: string) => {
      setImages((prev) => {
        const target = prev.find((i) => i.id === id);
        if (target && sessionId) {
          void sendRpc("image.detach", {
            session_id: sessionId,
            path: target.serverPath,
          }).catch(() => {
            /* best-effort: el chip ya se quita localmente */
          });
        }
        return prev.filter((i) => i.id !== id);
      });
    },
    [sendRpc, sessionId],
  );

  const clear = useCallback(() => {
    setImages([]);
    setError(null);
  }, []);

  return { images, addImage, removeImage, clear, uploading, error };
}
