import { useMemo, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";

import { MediaAttachment } from "@/components/MediaAttachment";

/**
 * Lightweight markdown renderer for LLM output.
 * Handles: code blocks, inline code, bold, italic, headers, links, lists, horizontal rules.
 * NOT a full CommonMark parser — optimized for typical assistant message patterns.
 *
 * `streaming` renders a blinking caret at the tail of the last block so it
 * appears to hug the final character instead of wrapping onto a new line
 * after a block element (paragraph/list/code/…).
 */
export function Markdown({
  content,
  highlightTerms,
  streaming,
}: {
  content: string;
  highlightTerms?: string[];
  streaming?: boolean;
}) {
  const blocks = useMemo(() => parseBlocks(content), [content]);
  const caret = streaming ? <StreamingCaret /> : null;

  return (
    <div className="text-sm text-foreground leading-relaxed space-y-2">
      {blocks.map((block, i) => (
        <Block
          key={i}
          block={block}
          highlightTerms={highlightTerms}
          caret={caret && i === blocks.length - 1 ? caret : null}
        />
      ))}
      {blocks.length === 0 && caret}
    </div>
  );
}

function StreamingCaret() {
  return (
    <span
      aria-hidden
      className="inline-block w-[0.5em] h-[1em] ml-0.5 align-[-0.15em] bg-foreground/50 animate-pulse"
    />
  );
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Align = "left" | "right" | "center" | "";

type BlockNode =
  | { type: "code"; lang: string; content: string }
  | { type: "heading"; level: number; content: string }
  | { type: "hr" }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "blockquote"; content: string }
  | { type: "table"; headers: string[]; aligns: Align[]; rows: string[][] }
  | { type: "paragraph"; content: string };

/* ------------------------------------------------------------------ */
/*  Block parser                                                       */
/* ------------------------------------------------------------------ */

function parseBlocks(text: string): BlockNode[] {
  const lines = text.split("\n");
  const blocks: BlockNode[] = [];
  let i = 0;

  const isBlockquote = (s: string) => /^>\s?/.test(s);
  const splitTableRow = (row: string) =>
    row
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());
  const isTableSep = (s: string) => {
    if (!s.includes("-")) return false;
    const cells = splitTableRow(s);
    return cells.length > 0 && cells.every((c) => /^:?-+:?$/.test(c));
  };
  const isTableStart = (idx: number) =>
    idx + 1 < lines.length &&
    lines[idx].includes("|") &&
    isTableSep(lines[idx + 1]);

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    const fenceMatch = line.match(/^```(\w*)/);
    if (fenceMatch) {
      const lang = fenceMatch[1] || "";
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push({ type: "code", lang, content: codeLines.join("\n") });
      continue;
    }

    // Heading
    const headingMatch = line.match(/^(#{1,4})\s+(.+)/);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        content: headingMatch[2],
      });
      i++;
      continue;
    }

    // Horizontal rule
    if (/^[-*_]{3,}\s*$/.test(line)) {
      blocks.push({ type: "hr" });
      i++;
      continue;
    }

    // Unordered list
    if (/^[-*+]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*+]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*+]\s/, ""));
        i++;
      }
      blocks.push({ type: "list", ordered: false, items });
      continue;
    }

    // Ordered list
    if (/^\d+[.)]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+[.)]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+[.)]\s/, ""));
        i++;
      }
      blocks.push({ type: "list", ordered: true, items });
      continue;
    }

    // Blockquote
    if (isBlockquote(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && isBlockquote(lines[i])) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      blocks.push({ type: "blockquote", content: quoteLines.join("\n") });
      continue;
    }

    // Table (GFM pipe table: header row + ---|--- separator + data rows)
    if (isTableStart(i)) {
      const headers = splitTableRow(line);
      const aligns: Align[] = splitTableRow(lines[i + 1]).map((s) => {
        const l = s.startsWith(":");
        const r = s.endsWith(":");
        return l && r ? "center" : r ? "right" : l ? "left" : "";
      });
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
        rows.push(splitTableRow(lines[i]));
        i++;
      }
      blocks.push({ type: "table", headers, aligns, rows });
      continue;
    }

    // Empty line
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph — collect consecutive non-empty, non-special lines
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].match(/^```/) &&
      !lines[i].match(/^#{1,4}\s/) &&
      !lines[i].match(/^[-*+]\s/) &&
      !lines[i].match(/^\d+[.)]\s/) &&
      !lines[i].match(/^[-*_]{3,}\s*$/) &&
      !isBlockquote(lines[i]) &&
      !isTableStart(i)
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      blocks.push({ type: "paragraph", content: paraLines.join("\n") });
    }
  }

  return blocks;
}

/* ------------------------------------------------------------------ */
/*  Block renderer                                                     */
/* ------------------------------------------------------------------ */

/** Fenced code block with a ChatGPT-style header bar: language label on the
 *  left, a one-click "Copiar" button on the right. */
function CodeBlock({
  lang,
  content,
  caret,
}: {
  lang: string;
  content: string;
  caret?: ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard denied — leave the label as-is */
    }
  };
  return (
    <div className="overflow-hidden rounded-md border border-border bg-secondary/60">
      <div className="flex items-center justify-between border-b border-border/60 bg-muted/40 px-3 py-1">
        <span className="select-none font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
          {lang || "código"}
        </span>
        <button
          type="button"
          onClick={copy}
          aria-label="Copiar código"
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
          {copied ? "Copiado" : "Copiar"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 py-2.5 text-xs font-mono leading-relaxed">
        <code>
          {content}
          {caret}
        </code>
      </pre>
    </div>
  );
}

function Block({
  block,
  highlightTerms,
  caret,
}: {
  block: BlockNode;
  highlightTerms?: string[];
  caret?: ReactNode;
}) {
  switch (block.type) {
    case "code":
      return <CodeBlock lang={block.lang} content={block.content} caret={caret} />;

    case "heading": {
      const Tag = `h${Math.min(block.level, 4)}` as "h1" | "h2" | "h3" | "h4";
      const sizes: Record<string, string> = {
        h1: "text-base font-bold",
        h2: "text-sm font-bold",
        h3: "text-sm font-semibold",
        h4: "text-sm font-medium",
      };
      return (
        <Tag className={sizes[Tag]}>
          <InlineContent text={block.content} highlightTerms={highlightTerms} />
          {caret}
        </Tag>
      );
    }

    case "hr":
      return (
        <>
          <hr className="border-border" />
          {caret}
        </>
      );

    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      const last = block.items.length - 1;
      return (
        <Tag
          className={`space-y-0.5 ${block.ordered ? "list-decimal" : "list-disc"} pl-5 text-sm`}
        >
          {block.items.map((item, i) => (
            <li key={i}>
              <InlineContent text={item} highlightTerms={highlightTerms} />
              {i === last ? caret : null}
            </li>
          ))}
        </Tag>
      );
    }

    case "blockquote":
      return (
        <blockquote className="border-l-2 border-border pl-3 italic text-muted-foreground">
          <InlineContent text={block.content} highlightTerms={highlightTerms} />
          {caret}
        </blockquote>
      );

    case "table":
      return (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {block.headers.map((h, i) => {
                  const a = block.aligns[i];
                  return (
                    <th
                      key={i}
                      className="border border-border bg-muted/40 px-2 py-1 text-left font-semibold"
                      style={a ? { textAlign: a } : undefined}
                    >
                      <InlineContent text={h} highlightTerms={highlightTerms} />
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => {
                    const a = block.aligns[c];
                    return (
                      <td
                        key={c}
                        className="border border-border px-2 py-1 align-top"
                        style={a ? { textAlign: a } : undefined}
                      >
                        <InlineContent text={cell} highlightTerms={highlightTerms} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );

    case "paragraph":
      return (
        <p>
          <InlineContent text={block.content} highlightTerms={highlightTerms} />
          {caret}
        </p>
      );
  }
}

/* ------------------------------------------------------------------ */
/*  Inline parser + renderer                                           */
/* ------------------------------------------------------------------ */

type InlineNode =
  | { type: "text"; content: string }
  | { type: "code"; content: string }
  | { type: "bold"; content: string }
  | { type: "italic"; content: string }
  | { type: "link"; text: string; href: string }
  | { type: "media"; alt: string; href: string }
  | { type: "br" };

const _MD_IMG_EXT = /\.(png|jpe?g|gif|webp|svg|bmp|avif)(?:[?#]|$)/i;
const _MD_VID_EXT = /\.(mp4|webm|mov|m4v|ogv|ogg)(?:[?#]|$)/i;

/** For `/artifacts/download?path=<file>` links the extension is in the query. */
function _mediaProbe(src: string): string {
  const q = src.indexOf("path=");
  if (q !== -1) {
    try {
      return decodeURIComponent(src.slice(q + 5));
    } catch {
      return src.slice(q + 5);
    }
  }
  return src;
}
function isVideoSrc(src: string): boolean {
  return _MD_VID_EXT.test(src) || _MD_VID_EXT.test(_mediaProbe(src));
}
function isMediaUrl(src: string): boolean {
  const probe = _mediaProbe(src);
  return (
    _MD_IMG_EXT.test(src) ||
    _MD_VID_EXT.test(src) ||
    _MD_IMG_EXT.test(probe) ||
    _MD_VID_EXT.test(probe)
  );
}
/** http(s) or same-origin relative path — safe to use as media src / link href. */
function isSafeRef(src: string): boolean {
  return /^https?:\/\//i.test(src) || src.startsWith("/");
}

/** Un path de filesystem local referido por el agente (/root/…, ~/…,
 *  file://…) no es cargable por el browser: se puentea por el endpoint del
 *  backend GET /media/local?path=… (allowlist ~/.clawksis/{audio_cache,
 *  cache/images,artifacts}). Las refs same-origin que el dashboard ya sirve
 *  (/artifacts/, /api/, /media/, assets) y las http(s) pasan intactas. */
function toServableSrc(src: string): string {
  let p = src.trim();
  let fileScheme = false;
  if (/^file:\/\//i.test(p)) {
    fileScheme = true;
    p = p.replace(/^file:\/\//i, "");
    try {
      p = decodeURIComponent(p);
    } catch {
      /* % literal en el path — se usa tal cual */
    }
  }
  const servable = [
    "/artifacts/",
    "/api/",
    "/media/",
    "/assets/",
    "/ds-assets/",
    "/fonts",
  ];
  const localFs =
    fileScheme ||
    p.startsWith("~/") ||
    (p.startsWith("/") &&
      !servable.some((k) => p.startsWith(k)) &&
      p.indexOf("/", 1) !== -1);
  return localFs ? "/media/local?path=" + encodeURIComponent(p) : src;
}

function parseInline(text: string): InlineNode[] {
  const nodes: InlineNode[] = [];
  // Pattern priority: image > code > link > bold > italic > bare URL > line break
  const pattern =
    /(!\[([^\]]*)\]\(([^)]+)\))|(`[^`]+`)|(\[([^\]]+)\]\(([^)]+)\))|(\*\*([^*]+)\*\*)|(\*([^*]+)\*)|(\bhttps?:\/\/[^\s<>)\]]+)|(\n)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push({ type: "text", content: text.slice(lastIndex, match.index) });
    }

    if (match[1]) {
      // ![alt](url) image / video → rendered inline as media
      nodes.push({ type: "media", alt: match[2] ?? "", href: match[3] });
    } else if (match[4]) {
      // Inline code
      nodes.push({ type: "code", content: match[4].slice(1, -1) });
    } else if (match[5]) {
      // [text](url) — image/video links render inline as media (the agent
      // sometimes LINKS a generated image instead of using ![]()); else a link.
      if (isMediaUrl(match[7])) {
        nodes.push({ type: "media", alt: match[6] ?? "", href: match[7] });
      } else {
        nodes.push({ type: "link", text: match[6], href: match[7] });
      }
    } else if (match[8]) {
      // **bold**
      nodes.push({ type: "bold", content: match[9] });
    } else if (match[10]) {
      // *italic*
      nodes.push({ type: "italic", content: match[11] });
    } else if (match[12]) {
      // Bare URL — image/video URLs render inline as media, rest as a link.
      const url = match[12];
      if (isMediaUrl(url)) {
        nodes.push({ type: "media", alt: "", href: url });
      } else {
        nodes.push({ type: "link", text: url, href: url });
      }
    } else if (match[13]) {
      // Line break within paragraph
      nodes.push({ type: "br" });
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push({ type: "text", content: text.slice(lastIndex) });
  }

  return nodes;
}

function InlineContent({
  text,
  highlightTerms,
}: {
  text: string;
  highlightTerms?: string[];
}) {
  const nodes = useMemo(() => parseInline(text), [text]);

  return (
    <>
      {nodes.map((node, i) => {
        switch (node.type) {
          case "text":
            return (
              <HighlightedText
                key={i}
                text={node.content}
                terms={highlightTerms}
              />
            );
          case "code":
            return (
              <code
                key={i}
                className="rounded bg-secondary/60 px-1.5 py-0.5 text-xs font-mono text-primary/90"
              >
                {node.content}
              </code>
            );
          case "bold":
            return (
              <strong key={i} className="font-semibold">
                <HighlightedText text={node.content} terms={highlightTerms} />
              </strong>
            );
          case "italic":
            return (
              <em key={i}>
                <HighlightedText text={node.content} terms={highlightTerms} />
              </em>
            );
          case "link": {
            // Security: only render http(s)/mailto AND same-origin relative
            // links (/artifacts/download, /api/...). Other schemes
            // (javascript:, data:, vbscript:) are dropped to plain text so a
            // crafted link in agent/message content can't execute on click.
            const href = node.href.trim();
            if (!/^(https?:|mailto:)/i.test(href) && !href.startsWith("/")) {
              return (
                <HighlightedText
                  key={i}
                  text={node.text}
                  terms={highlightTerms}
                />
              );
            }
            return (
              <a
                key={i}
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-primary underline underline-offset-2 decoration-primary/30 hover:decoration-primary/60 transition-colors"
              >
                {node.text}
              </a>
            );
          }
          case "media": {
            // Imágenes/videos que el agente "manda": markdown ![](url), URLs
            // http(s) de media, o links same-origin /artifacts/download?path=…
            // Solo http(s) o relativo (same-origin); data:/javascript: caen a
            // texto (anti-XSS). Sirve para image_generate/video_generate y para
            // cualquier archivo de media bajo ~/clawksis_exports.
            const src = toServableSrc(node.href);
            if (!isSafeRef(src)) {
              return (
                <HighlightedText
                  key={i}
                  text={node.alt || src}
                  terms={highlightTerms}
                />
              );
            }
            return (
              <MediaAttachment
                key={i}
                src={src}
                alt={node.alt}
                video={isVideoSrc(src)}
                className="my-2"
              />
            );
          }
          case "br":
            return <br key={i} />;
        }
      })}
    </>
  );
}

/** Highlight search terms within a plain text string. */
function HighlightedText({ text, terms }: { text: string; terms?: string[] }) {
  if (!terms || terms.length === 0) return <>{text}</>;

  // Build a regex that matches any of the search terms (case-insensitive)
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(regex);

  return (
    <>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <mark key={i} className="bg-warning/30 text-warning px-0.5">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}
