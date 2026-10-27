// Skill settings form (`/api/skills/settings/{name}`): the `metadata.clawk.config`
// values a skill declares, saved under `skills.config.<key>` in the profile's
// config.yaml. Risky changes come back as 409 until the request carries
// `confirm: true`.

import { fetchJSON } from "./api";
import { ApiError } from "./api-error";

export type SkillSettingType = "bool" | "integer" | "number" | "text" | "choice";
export type SkillSettingValue = string | number | boolean | null;

export interface SkillSettingField {
  choice_labels?: Record<string, Record<string, string>>;
  choices?: string[];
  confirm?: boolean | string[];
  default?: SkillSettingValue;
  description: string;
  is_set: boolean;
  key: string;
  label?: Record<string, string>;
  max?: number;
  min?: number;
  type: SkillSettingType;
  value: SkillSettingValue;
}

export interface SkillSettings {
  fields: SkillSettingField[];
  name: string;
}

export type SaveResult =
  | { ok: true; changed: string[]; fields: SkillSettingField[] }
  | { ok: false; needsConfirmation: string[] };

const settingsPath = (name: string) =>
  `/api/skills/settings/${encodeURIComponent(name)}`;

export const skillSettingsApi = {
  get: (name: string) => fetchJSON<SkillSettings>(settingsPath(name)),
  save: async (
    name: string,
    values: Record<string, SkillSettingValue>,
    confirm = false,
  ): Promise<SaveResult> => {
    try {
      const result = await fetchJSON<{ changed: string[]; fields: SkillSettingField[] }>(
        settingsPath(name),
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ values, confirm }),
        },
      );
      return { ok: true, changed: result.changed, fields: result.fields };
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        try {
          const body = JSON.parse(err.body) as { needs_confirmation?: string[] };
          if (Array.isArray(body.needs_confirmation)) {
            return { ok: false, needsConfirmation: body.needs_confirmation };
          }
        } catch {
          /* not the confirmation envelope: rethrow below */
        }
      }
      throw err;
    }
  },
};

/** The field's name in `locale`: its label for that language, else any label, else the key. */
export function fieldLabel(field: SkillSettingField, locale: string): string {
  const labels = field.label ?? {};
  const lang = locale.toLowerCase().split(/[-_]/)[0];
  return labels[lang] ?? labels["*"] ?? labels.en ?? field.key.split(".").pop() ?? field.key;
}

/** A choice's name in `locale`, else the raw value. */
export function choiceLabel(field: SkillSettingField, choice: string, locale: string): string {
  const lang = locale.toLowerCase().split(/[-_]/)[0];
  return field.choice_labels?.[lang]?.[choice] ?? choice;
}
