import { useEffect, useMemo, useRef, useState } from "react";
import type { ChartPanel as ChartPanelData, DashboardSeries } from "@/lib/api-skill-dashboards";
import { formatCell } from "./format";

// Categorical slots (dark steps), validated as a set against the dashboard's
// dark surfaces: violet, orange, aqua, yellow. Assigned in this order, never cycled.
const SERIES_COLORS = ["#9085e9", "#d95926", "#199e70", "#c98500"];
const HEIGHT = 220;
const PAD = { top: 16, right: 16, bottom: 28, left: 48 };

type XKind = "time" | "number" | "category";

interface Scaled {
  domain: Array<string | number>;
  kind: XKind;
  x: (value: string | number) => number;
  y: (value: number) => number;
  yTicks: number[];
  baseline: number;
}

function xKind(series: DashboardSeries[]): XKind {
  const xs = series.flatMap((s) => s.points.map(([x]) => x));
  if (xs.every((x) => typeof x === "number")) return "number";
  if (xs.every((x) => typeof x === "string" && !Number.isNaN(Date.parse(x)))) return "time";
  return "category";
}

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) return [min];
  const step = 10 ** Math.floor(Math.log10((max - min) / count));
  const err = (max - min) / count / step;
  const nice = step * (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1);
  const ticks: number[] = [];
  for (let v = Math.ceil(min / nice) * nice; v <= max + nice / 2; v += nice) ticks.push(+v.toFixed(10));
  return ticks;
}

function scale(series: DashboardSeries[], kind: XKind, width: number, bar: boolean): Scaled {
  const xs = [...new Set(series.flatMap((s) => s.points.map(([x]) => x)))];
  const numeric = (x: string | number) => (kind === "time" ? Date.parse(String(x)) : Number(x));
  const domain = kind === "category" ? xs : [...xs].sort((a, b) => numeric(a) - numeric(b));
  const ys = series.flatMap((s) => s.points.map(([, y]) => y));
  const lo = Math.min(...ys, bar ? 0 : Infinity);
  const hi = Math.max(...ys, bar ? 0 : -Infinity);
  const yTicks = niceTicks(lo, hi === lo ? lo + 1 : hi);
  const y0 = Math.min(lo, yTicks[0]);
  const y1 = Math.max(hi, yTicks[yTicks.length - 1]);
  const plotW = Math.max(width - PAD.left - PAD.right, 1);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const y = (v: number) => PAD.top + plotH - ((v - y0) / (y1 - y0 || 1)) * plotH;
  const band = plotW / Math.max(domain.length, 1);
  const first = numeric(domain[0]);
  const span = numeric(domain[domain.length - 1]) - first || 1;
  const x =
    kind === "category" || bar
      ? (v: string | number) => PAD.left + band * (domain.indexOf(v) + 0.5)
      : (v: string | number) => PAD.left + ((numeric(v) - first) / span) * plotW;
  return { domain, kind, x, y, yTicks, baseline: y(Math.max(y0, Math.min(0, y1))) };
}

function xLabel(value: string | number, kind: XKind, locale: string): string {
  if (kind !== "time") return String(value);
  return new Date(String(value)).toLocaleDateString(locale, { month: "short", day: "numeric" });
}

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function barPath(x: number, y: number, w: number, base: number): string {
  const r = Math.min(4, w / 2, Math.abs(base - y));
  if (y >= base) return `M${x},${base}h${w}v${y - base}h${-w}z`;
  return `M${x},${base}V${y + r}q0,${-r} ${r},${-r}h${w - 2 * r}q${r},0 ${r},${r}V${base}z`;
}

interface ChartProps {
  copy: { showData: string; hideData: string; emptyPanel: string };
  locale: string;
  panel: ChartPanelData;
}

export function ChartPanel({ copy, locale, panel }: ChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const series = panel.series.filter((s) => s.points.length > 0);
  const bar = panel.kind === "bar";
  const kind = xKind(series);
  const s = useMemo(() => (series.length && width ? scale(series, kind, width, bar) : null), [series, kind, width, bar]);

  if (!series.length) return <p className="text-sm text-text-tertiary">{copy.emptyPanel}</p>;

  const valueAt = (entry: DashboardSeries, x: string | number) => entry.points.find(([px]) => px === x)?.[1];
  const onMove = (event: React.PointerEvent<SVGRectElement>) => {
    if (!s) return;
    const box = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - box.left + PAD.left;
    let best = 0;
    s.domain.forEach((d, i) => {
      if (Math.abs(s.x(d) - px) < Math.abs(s.x(s.domain[best]) - px)) best = i;
    });
    setHover(best);
  };
  const hovered = s && hover !== null ? s.domain[hover] : null;
  const groupW = s ? Math.min(24 * series.length, ((width - PAD.left - PAD.right) / s.domain.length) * 0.7) : 0;
  const barW = Math.max(groupW / series.length - 2, 2);

  return (
    <div className="flex flex-col gap-3">
      {series.length > 1 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary" aria-label="legend">
          {series.map((entry, i) => (
            <li key={entry.name} className="flex items-center gap-1.5">
              <span className="h-2 w-3 rounded-full" style={{ background: SERIES_COLORS[i] }} />
              {entry.name}
            </li>
          ))}
        </ul>
      )}
      <div ref={ref} className="relative w-full">
        {s && (
          <svg width={width} height={HEIGHT} role="img" aria-label={panel.title || panel.y_label}>
            {s.yTicks.map((tick) => (
              <g key={tick}>
                <line x1={PAD.left} x2={width - PAD.right} y1={s.y(tick)} y2={s.y(tick)} stroke="currentColor" strokeOpacity={0.1} />
                <text x={PAD.left - 8} y={s.y(tick)} dy="0.32em" textAnchor="end" className="fill-current text-[10px] opacity-60">
                  {formatCell(tick, "number", locale)}
                </text>
              </g>
            ))}
            {[s.domain[0], s.domain[s.domain.length - 1]].map((d, i) => (
              <text key={i} x={s.x(d)} y={HEIGHT - 8} textAnchor={i ? "end" : "start"} className="fill-current text-[10px] opacity-60">
                {xLabel(d, s.kind, locale)}
              </text>
            ))}
            {series.map((entry, si) => {
              const color = SERIES_COLORS[si];
              const pts = s.domain.flatMap((d) => {
                const v = valueAt(entry, d);
                return v === undefined ? [] : [[s.x(d), s.y(v)] as const];
              });
              if (bar) {
                return s.domain.map((d) => {
                  const v = valueAt(entry, d);
                  if (v === undefined) return null;
                  const x = s.x(d) - groupW / 2 + si * (barW + 2);
                  return <path key={`${entry.name}-${d}`} d={barPath(x, s.y(v), barW, s.baseline)} fill={color} />;
                });
              }
              const last = pts[pts.length - 1];
              return (
                <g key={entry.name}>
                  <path
                    d={pts.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join("")}
                    fill="none"
                    stroke={color}
                    strokeWidth={2}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                  {last && <circle cx={last[0]} cy={last[1]} r={4} fill={color} stroke="var(--background-base, #0b0a14)" strokeWidth={2} />}
                </g>
              );
            })}
            {hovered !== null && (
              <line x1={s.x(hovered)} x2={s.x(hovered)} y1={PAD.top} y2={HEIGHT - PAD.bottom} stroke="currentColor" strokeOpacity={0.35} />
            )}
            <rect
              x={PAD.left}
              y={PAD.top}
              width={Math.max(width - PAD.left - PAD.right, 0)}
              height={HEIGHT - PAD.top - PAD.bottom}
              fill="transparent"
              onPointerMove={onMove}
              onPointerLeave={() => setHover(null)}
            />
          </svg>
        )}
        {s && hovered !== null && (
          <div
            className="clawk-liquid-chip pointer-events-none absolute top-2 z-10 min-w-32 rounded-xl border border-white/10 bg-background-base/90 px-3 py-2 text-xs shadow-lg"
            style={{ left: Math.min(Math.max(s.x(hovered) + 12, 0), Math.max(width - 160, 0)) }}
          >
            <div className="mb-1 text-text-tertiary">{xLabel(hovered, s.kind, locale)}</div>
            {series.map((entry, i) => (
              <div key={entry.name} className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5 text-text-secondary">
                  <span className="h-2 w-2 rounded-full" style={{ background: SERIES_COLORS[i] }} />
                  {entry.name || panel.y_label}
                </span>
                <span className="font-mono-ui text-text-primary">{formatCell(valueAt(entry, hovered) ?? null, "number", locale)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <ChartTable copy={copy} locale={locale} panel={panel} series={series} open={showTable} onToggle={() => setShowTable((v) => !v)} />
    </div>
  );
}

function ChartTable({
  copy,
  locale,
  onToggle,
  open,
  panel,
  series,
}: ChartProps & { onToggle: () => void; open: boolean; series: DashboardSeries[] }) {
  const xs = [...new Set(series.flatMap((s) => s.points.map(([x]) => x)))];
  return (
    <div>
      <button type="button" onClick={onToggle} className="text-xs text-text-tertiary underline-offset-2 hover:text-midground hover:underline">
        {open ? copy.hideData : copy.showData}
      </button>
      {open && (
        <table className="mt-2 w-full text-xs">
          <thead>
            <tr className="text-left text-text-tertiary">
              <th className="py-1 pr-3 font-normal">{panel.x_label || "x"}</th>
              {series.map((entry) => (
                <th key={entry.name} className="py-1 pr-3 text-right font-normal">{entry.name || panel.y_label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {xs.map((x) => (
              <tr key={String(x)} className="border-t border-current/5">
                <td className="py-1 pr-3">{String(x)}</td>
                {series.map((entry) => (
                  <td key={entry.name} className="py-1 pr-3 text-right font-mono-ui">
                    {formatCell(entry.points.find(([px]) => px === x)?.[1] ?? null, "number", locale)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
