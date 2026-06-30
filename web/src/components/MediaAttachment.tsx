import { Download } from "lucide-react";

/** Derive a sensible download filename from a media src.
 *  `/artifacts/download?path=/exports/dragon.png` -> `dragon.png`
 *  `https://cdn/x/y/clip.mp4`                      -> `clip.mp4`
 */
export function mediaFilename(src: string): string {
  try {
    const m = src.match(/[?&]path=([^&]+)/);
    const p = m ? decodeURIComponent(m[1]) : src.split(/[?#]/)[0];
    const base = p.split(/[\\/]/).filter(Boolean).pop();
    return base || "media";
  } catch {
    return "media";
  }
}

/** Inline image/video with a hover "download" affordance.
 *  Shared by the Markdown renderer and the chat tool-result media row so the
 *  user can always save what the agent generated (image_generate /
 *  video_generate / any media link). Same-origin `/artifacts/download` saves
 *  directly via the `download` attribute; cross-origin opens in a new tab.
 */
export function MediaAttachment({
  src,
  alt,
  video,
  className,
}: {
  src: string;
  alt?: string;
  video?: boolean;
  className?: string;
}) {
  const name = mediaFilename(src);
  return (
    <div className={"group relative inline-block " + (className ?? "")}>
      {video ? (
        <video
          src={src}
          controls
          preload="metadata"
          className="block max-h-[28rem] max-w-full rounded-lg border border-border"
        />
      ) : (
        <img
          src={src}
          alt={alt ?? "media"}
          loading="lazy"
          className="block max-h-[28rem] max-w-full rounded-lg border border-border"
        />
      )}
      <a
        href={src}
        download={name}
        target="_blank"
        rel="noreferrer"
        title={"Descargar " + name}
        aria-label={"Descargar " + name}
        className="absolute right-2 top-2 flex items-center gap-1 rounded-md bg-black/55 px-2 py-1 text-xs font-medium text-white opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100 focus-visible:opacity-100 hover:bg-black/75"
      >
        <Download className="size-3.5" />
        <span className="hidden sm:inline">Descargar</span>
      </a>
    </div>
  );
}
