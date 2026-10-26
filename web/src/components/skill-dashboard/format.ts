import type {
  DashboardCell,
  DashboardColumnFormat,
  DashboardTone,
} from "@/lib/api-skill-dashboards";

const EMPTY = "—";

function asNumber(value: DashboardCell): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function formatDate(value: DashboardCell, locale: string): string {
  if (typeof value !== "string" && typeof value !== "number") return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}

const NUMBER_FORMATTERS: Record<
  Exclude<DashboardColumnFormat, "text" | "datetime">,
  (n: number, locale: string) => string
> = {
  money: (n, locale) =>
    new Intl.NumberFormat(locale, { style: "currency", currency: "USD" }).format(n),
  number: (n, locale) =>
    new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(n),
  percent: (n, locale) =>
    `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(n)}%`,
};

/** A snapshot cell as text: numbers by column format (money is USD, percent is
 *  already in percent units), ISO strings as local dates, empty as an em dash. */
export function formatCell(
  value: DashboardCell,
  format: DashboardColumnFormat,
  locale: string,
): string {
  if (value === null || value === "") return EMPTY;
  if (typeof value === "boolean") return value ? "✓" : "✗";
  if (format === "datetime") return formatDate(value, locale);
  if (format === "text") return String(value);
  const n = asNumber(value);
  return n === null ? String(value) : NUMBER_FORMATTERS[format](n, locale);
}

/** A stat value: numbers get grouping, text passes through. */
export function formatStat(value: DashboardCell, locale: string): string {
  return typeof value === "number" ? formatCell(value, "number", locale) : formatCell(value, "text", locale);
}

const RELATIVE_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** "5 minutes ago" for an ISO timestamp; "" when it doesn't parse. */
export function relativeTime(iso: string, locale: string, now = Date.now()): string {
  const at = Date.parse(iso);
  if (!iso || Number.isNaN(at)) return "";
  // A writer's clock slightly ahead of ours reads as "now", never "in 3 minutes".
  const seconds = Math.min(Math.round((at - now) / 1000), 0);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [unit, size] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return rtf.format(seconds, "second");
}

export const TONE_TEXT: Record<DashboardTone, string> = {
  positive: "text-emerald-300",
  negative: "text-rose-300",
  warning: "text-amber-300",
  neutral: "text-text-secondary",
};

export const TONE_DOT: Record<DashboardTone, string> = {
  positive: "bg-emerald-400",
  negative: "bg-rose-400",
  warning: "bg-amber-400",
  neutral: "bg-current/30",
};
