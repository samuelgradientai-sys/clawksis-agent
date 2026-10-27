import { useCallback, useEffect, useMemo, useState } from "react";
import { Settings2, ShieldAlert } from "lucide-react";
import { Input } from "@nous-research/ui/ui/components/input";
import { Select, SelectOption } from "@nous-research/ui/ui/components/select";
import { Switch } from "@nous-research/ui/ui/components/switch";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { errorMessage } from "@/lib/api-error";
import {
  choiceLabel,
  fieldLabel,
  skillSettingsApi,
  type SkillSettingField,
  type SkillSettingValue,
} from "@/lib/api-skill-settings";
import type { SkillDashboardsCopy } from "@/i18n/types";
import { fill } from "./copy";

type Draft = Record<string, string | boolean>;

function draftValue(field: SkillSettingField): string | boolean {
  if (field.type === "bool") return field.value === true;
  return field.value === null || field.value === undefined ? "" : String(field.value);
}

function toDraft(fields: SkillSettingField[]): Draft {
  return Object.fromEntries(fields.map((f) => [f.key, draftValue(f)]));
}

function shownValue(field: SkillSettingField, value: string | boolean, copy: SkillDashboardsCopy, locale: string): string {
  if (field.type === "bool") return value === true ? copy.settingsOn : copy.settingsOff;
  if (field.type === "choice") return choiceLabel(field, String(value), locale);
  return String(value);
}

/** Form for the settings a skill declares (`metadata.clawk.config`). Changes the skill marks as
 *  risky (turning trading on, a real-money account, a higher limit) ask for confirmation first. */
export function SkillSettingsCard({
  copy,
  locale,
  name,
  onSaved,
}: {
  copy: SkillDashboardsCopy;
  locale: string;
  name: string;
  onSaved?: () => void;
}) {
  const [fields, setFields] = useState<SkillSettingField[] | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<string[] | null>(null);

  const reset = useCallback((next: SkillSettingField[]) => {
    setFields(next);
    setDraft(toDraft(next));
  }, []);

  useEffect(() => {
    // The page keys this card by skill name, so a new skill mounts a fresh card.
    let alive = true;
    skillSettingsApi
      .get(name)
      .then((s) => alive && reset(s.fields))
      .catch((err) => alive && setError(errorMessage(err)));
    return () => {
      alive = false;
    };
  }, [name, reset]);

  const changed = useMemo(() => {
    if (!fields) return {};
    const original = toDraft(fields);
    return Object.fromEntries(
      Object.entries(draft).filter(([key, value]) => value !== original[key]),
    ) as Record<string, SkillSettingValue>;
  }, [draft, fields]);
  const dirty = Object.keys(changed).length > 0;

  if (!fields || fields.length === 0) {
    return error ? (
      <p className="rounded-2xl border border-rose-400/30 bg-rose-400/10 px-4 py-2 text-sm text-rose-200">{error}</p>
    ) : null;
  }

  const save = async (confirm: boolean) => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const result = await skillSettingsApi.save(name, changed, confirm);
      if (!result.ok) {
        setPendingConfirm(result.needsConfirmation);
        return;
      }
      setPendingConfirm(null);
      reset(result.fields);
      setNotice(result.changed.length ? copy.settingsSaved : copy.settingsNoChanges);
      onSaved?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const byKey = Object.fromEntries(fields.map((f) => [f.key, f]));
  const confirmText = (pendingConfirm ?? [])
    .map((key) => {
      const field = byKey[key];
      return field ? `${fieldLabel(field, locale)} → ${shownValue(field, draft[key], copy, locale)}` : key;
    })
    .join("; ");

  return (
    <section className="clawk-liquid-panel rounded-3xl border border-white/10 px-5 py-4">
      <div className="mb-3 flex items-start gap-3">
        <Settings2 className="mt-0.5 h-5 w-5 shrink-0 text-midground" />
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-text-primary">{copy.settingsTitle}</h2>
          <p className="text-xs text-text-tertiary">{copy.settingsHint}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
        {fields.map((field) => (
          <SettingRow
            key={field.key}
            copy={copy}
            field={field}
            locale={locale}
            value={draft[field.key]}
            onChange={(value) => setDraft((d) => ({ ...d, [field.key]: value }))}
          />
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!dirty || saving}
          onClick={() => void save(false)}
          className="clawk-liquid-chip rounded-full px-4 py-1.5 text-sm font-medium text-text-primary transition-colors hover:text-midground disabled:opacity-40"
        >
          {saving ? copy.settingsSaving : copy.settingsSave}
        </button>
        {dirty && !saving && (
          <button
            type="button"
            onClick={() => reset(fields)}
            className="text-sm text-text-tertiary hover:text-midground"
          >
            {copy.settingsReset}
          </button>
        )}
        {notice && !dirty && <span className="text-sm text-emerald-300">{notice}</span>}
        {error && <span className="text-sm text-rose-300">{error}</span>}
      </div>

      <ConfirmDialog
        open={pendingConfirm !== null}
        destructive
        loading={saving}
        title={copy.settingsConfirmTitle}
        description={fill(copy.settingsConfirmBody, { changes: confirmText })}
        confirmLabel={copy.settingsConfirmAction}
        cancelLabel={copy.settingsCancel}
        onCancel={() => setPendingConfirm(null)}
        onConfirm={() => void save(true)}
      />
    </section>
  );
}

function SettingRow({
  copy,
  field,
  locale,
  onChange,
  value,
}: {
  copy: SkillDashboardsCopy;
  field: SkillSettingField;
  locale: string;
  onChange: (value: string | boolean) => void;
  value: string | boolean;
}) {
  const label = fieldLabel(field, locale);
  const id = `skill-setting-${field.key.replace(/[^\w-]/g, "-")}`;
  const hint = (
    <span className="flex flex-wrap items-center gap-x-2 text-xs text-text-tertiary">
      <span>{field.description}</span>
      {field.default !== undefined && field.default !== null && field.default !== "" && (
        <span className="opacity-80">
          · {fill(copy.settingsDefault, { value: shownValue(field, field.type === "bool" ? field.default === true : String(field.default), copy, locale) })}
        </span>
      )}
      {field.confirm && (
        <span className="inline-flex items-center gap-1 text-amber-300/90">
          <ShieldAlert className="h-3 w-3" /> {copy.settingsNeedsConfirm}
        </span>
      )}
    </span>
  );

  if (field.type === "bool") {
    return (
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-0.5">
          <label htmlFor={id} className="text-sm text-text-primary">{label}</label>
          {hint}
        </div>
        <Switch id={id} checked={value === true} onCheckedChange={(v: boolean) => onChange(v)} />
      </div>
    );
  }

  let control;
  if (field.type === "choice") {
    const current = String(value);
    // A value saved outside the declared choices stays visible instead of silently changing.
    const options = [...(field.choices ?? [])];
    if (current && !options.includes(current)) options.unshift(current);
    control = (
      <Select value={current} onValueChange={(v: string) => onChange(v)}>
        {!current && <SelectOption value="">—</SelectOption>}
        {options.map((choice) => (
          <SelectOption key={choice} value={choice}>
            {choiceLabel(field, choice, locale)}
          </SelectOption>
        ))}
      </Select>
    );
  } else {
    const numeric = field.type === "integer" || field.type === "number";
    control = (
      <Input
        id={id}
        type={numeric ? "number" : "text"}
        inputMode={numeric ? "decimal" : undefined}
        min={field.min}
        max={field.max}
        step={field.type === "integer" ? 1 : undefined}
        value={String(value)}
        placeholder={field.type === "text" ? field.description : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-sm text-text-primary">{label}</label>
      {control}
      {hint}
    </div>
  );
}
