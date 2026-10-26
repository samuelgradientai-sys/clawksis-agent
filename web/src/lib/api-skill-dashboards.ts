// Skill mini dashboards (`/api/skills/dashboards`). A skill that declares
// `metadata.clawk.dashboard` writes a version-1 snapshot under its profile's
// home; the backend clips it to these shapes before it reaches the browser.

import { fetchJSON } from "./api";

export type DashboardTone = "positive" | "negative" | "warning" | "neutral";
export type DashboardCell = string | number | boolean | null;
export type DashboardColumnFormat =
  | "text"
  | "number"
  | "money"
  | "percent"
  | "datetime";

export interface SkillDashboardSummary {
  category: string;
  description: string;
  emoji: string;
  enabled: boolean;
  modified_at: string;
  name: string;
  snapshot_file: string;
  title: string;
}

interface PanelBase {
  description: string;
  id: string;
  title: string;
  width: "full" | "half";
}

export interface DashboardStat {
  hint: string;
  label: string;
  tone: DashboardTone;
  value: DashboardCell;
}

export interface DashboardColumn {
  align: "left" | "right";
  format: DashboardColumnFormat;
  key: string;
  label: string;
}

export type DashboardRow = Record<string, DashboardCell> & {
  _tone: DashboardTone;
};

export interface DashboardListItem {
  body: string;
  meta: string;
  title: string;
  tone: DashboardTone;
}

export interface DashboardSeries {
  name: string;
  points: Array<[string | number, number]>;
}

export interface StatsPanel extends PanelBase {
  items: DashboardStat[];
  type: "stats";
}

export interface TablePanel extends PanelBase {
  columns: DashboardColumn[];
  empty: string;
  rows: DashboardRow[];
  type: "table";
}

export interface ListPanel extends PanelBase {
  empty: string;
  items: DashboardListItem[];
  type: "list";
}

export interface ChartPanel extends PanelBase {
  kind: "line" | "bar";
  series: DashboardSeries[];
  type: "chart";
  x_label: string;
  y_label: string;
}

export interface TextPanel extends PanelBase {
  body: string;
  type: "text";
}

export interface UnsupportedPanel extends PanelBase {
  original_type: string;
  type: "unsupported";
}

export type DashboardPanel =
  | StatsPanel
  | TablePanel
  | ListPanel
  | ChartPanel
  | TextPanel
  | UnsupportedPanel;

export interface SkillDashboardSnapshot {
  panels: DashboardPanel[];
  subtitle: string;
  title: string;
  updated_at: string;
  version: 1;
}

export interface SkillDashboardDetail extends SkillDashboardSummary {
  error: string | null;
  snapshot: SkillDashboardSnapshot | null;
}

export const skillDashboardsApi = {
  list: () =>
    fetchJSON<{ dashboards: SkillDashboardSummary[] }>(
      "/api/skills/dashboards",
    ),
  get: (name: string) =>
    fetchJSON<SkillDashboardDetail>(
      `/api/skills/dashboards/${encodeURIComponent(name)}`,
    ),
};

/** `/api/skills` rows carry this flag; kept here so the api.ts facade doesn't grow. */
export interface SkillDashboardFlag {
  has_dashboard?: boolean;
}

export function skillDashboardPath(name: string): string {
  return `/skills/dashboards/${encodeURIComponent(name)}`;
}
