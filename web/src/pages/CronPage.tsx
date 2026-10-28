import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  type CronTriggerController,
  createCronTriggerController,
} from "@clawk/shared";
import { Clock, X } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Select, SelectOption } from "@nous-research/ui/ui/components/select";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { H2 } from "@nous-research/ui/ui/components/typography/h2";
import { api, getManagementProfile } from "@/lib/api";
import type {
  CronJob,
  CronDeliveryTarget,
  CronJobMutation,
  ModelOptionsResult,
  ProfileInfo,
  SkillInfo,
  ToolsetInfo,
} from "@/lib/api";
import {
  buildCronJobPayload,
  splitCronList,
  cronJobHasExecutionContent,
  cronAgoLabel,
  cronSchedulerStaleAgeS,
  cronJobFormFromJob,
  focusCronField,
  type CronJobFormState,
} from "@/lib/cron-job";
import {
  getJobKey,
  getJobProfile,
  getJobState,
  getJobTitle,
  splitJobKey,
  truncateText,
} from "@/lib/cron-job-view";
import { CronJobCard } from "@/components/CronJobCard";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { CronCalendar } from "@/components/CronCalendar";
import {
  DEFAULT_SCHEDULE_STATE,
  ScheduleBuilder,
} from "@/components/ScheduleBuilder";
import {
  buildScheduleString,
  englishOrdinal,
  parseScheduleString,
  type ScheduleBuilderState,
  type ScheduleDescribeStrings,
} from "@/lib/schedule";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { useConfirmDelete } from "@nous-research/ui/hooks/use-confirm-delete";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { useCronArchiveChats } from "@/hooks/useCronArchiveChats";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { Switch } from "@nous-research/ui/ui/components/switch";
import { useI18n } from "@/i18n";
import type { Translations } from "@/i18n/types";
import { en } from "@/i18n/en";
import { usePageHeader } from "@/contexts/usePageHeader";
import { PluginSlot } from "@/plugins";
import { LoadErrorNotice } from "@/components/LoadErrorNotice";
import { Segmented } from "@nous-research/ui/ui/components/segmented";
import { AutomationBlueprints } from "@/components/AutomationBlueprints";
import { cn, themedBody } from "@/lib/utils";
import { errorMessage } from "@/lib/api-error";

function NameCheckboxPicker({
  id,
  available,
  selected,
  onChange,
  emptyLabel,
}: {
  id: string;
  available: Array<{ name: string; description?: string | null }>;
  selected: string[];
  onChange: (names: string[]) => void;
  emptyLabel: string;
}) {
  const names = available.map((item) => item.name);
  const orphaned = selected.filter((s) => !names.includes(s));
  const all = [...orphaned.map((name) => ({ name, description: "" })), ...available];

  if (all.length === 0) {
    return <p className="text-xs text-muted-foreground">{emptyLabel}</p>;
  }

  const toggle = (name: string, checked: boolean) => {
    if (checked) onChange([...selected, name]);
    else onChange(selected.filter((s) => s !== name));
  };

  return (
    <div
      id={id}
      className="max-h-36 overflow-y-auto border border-border bg-background/40 p-1"
    >
      {all.map((item) => (
        <label
          key={item.name}
          className="flex cursor-pointer items-center gap-2 px-2 py-1 text-xs hover:bg-muted/40"
          title={item.description || undefined}
        >
          <input
            type="checkbox"
            className="accent-foreground"
            checked={selected.includes(item.name)}
            onChange={(e) => toggle(item.name, e.target.checked)}
          />
          <span className="font-mono-ui truncate">{item.name}</span>
        </label>
      ))}
    </div>
  );
}

interface CronJobEditorState extends CronJobFormState {
  scheduleState: ScheduleBuilderState;
  // Clawksis extensions: finite repeat count (create only), per-job model
  // fallback chain ("provider:model, ..."), the "no news" notice and the
  // SOUL.md / USER.md / MEMORY.md context toggles.
  repeat: string;
  fallback_models: string;
  silent_notice: boolean;
  use_soul: boolean;
  use_user_md: boolean;
  use_memory: boolean;
  run_in_chat: boolean;
  browser: string;
}

/** English fallbacks for the Clawksis cron labels (optional in most locales). */
interface CronExtraLabels {
  silentNotice: string;
  useSoul: string;
  useUserMd: string;
  useMemory: string;
  runInChat: string;
  runInChatHint: string;
  browser: string;
  browserAuto: string;
  browserMyChrome: string;
  browserServer: string;
  browserHint: string;
  contextToggles: string;
  fallbackModels: string;
  fallbackModelsHint: string;
  viewLabel: string;
  listView: string;
  calendarView: string;
  archiveChats: string;
  archiveChatsHint: string;
}

function cronExtraLabels(t: Translations): CronExtraLabels {
  return {
    silentNotice: t.cron.silentNotice ?? "Notify even when there's nothing new",
    useSoul: t.cron.useSoul ?? "Use SOUL.md (assistant identity)",
    useUserMd: t.cron.useUserMd ?? "Use USER.md (user profile)",
    useMemory: t.cron.useMemory ?? "Use MEMORY.md (long-term memory)",
    runInChat: t.cron.runInChat ?? "Run it in my chat, as if I had sent it",
    browser: t.cron.browser ?? "Browser",
    browserAuto: t.cron.browserAuto ?? "Automatic (my Chrome when it is connected)",
    browserMyChrome: t.cron.browserMyChrome ?? "Only my Chrome (stops if it is offline)",
    browserServer: t.cron.browserServer ?? "The server's browser (never my Chrome)",
    browserHint:
      t.cron.browserHint ??
      "Sites where you are logged in (LinkedIn, Instagram, your bank) must use your Chrome, or they block the account.",
    runInChatHint:
      t.cron.runInChatHint ??
      "The instruction arrives in the delivery chat and the agent runs it there with the whole conversation, memory and every tool, and answers you right there. Off: it runs as an isolated background task that only sends its result.",
    contextToggles: t.cron.contextToggles ?? "Context & delivery",
    fallbackModels: t.cron.fallbackModels ?? "Fallback models (optional)",
    fallbackModelsHint:
      t.cron.fallbackModelsHint ??
      "If the primary model fails, retry with these. Format provider:model, comma-separated.",
    viewLabel: t.cron.viewLabel ?? "View",
    listView: t.cron.listView ?? "List",
    calendarView: t.cron.calendarView ?? "Calendar",
    archiveChats: t.cron.archiveChats ?? "Archivar chats de cron",
    archiveChatsHint:
      t.cron.archiveChatsHint ??
      "Al terminar cada ejecución, su conversación se archiva (no llena la lista de chats)",
  };
}

interface CronJobFormResources {
  availableSkills: SkillInfo[];
  availableToolsets: ToolsetInfo[];
  modelOptions: ModelOptionsResult | null;
  deliveryTargets: CronDeliveryTarget[];
}

function emptyCronJobForm(): CronJobEditorState {
  return {
    name: "",
    prompt: "",
    schedule: "",
    deliver: "local",
    skills: [],
    provider: "",
    model: "",
    base_url: "",
    script: "",
    no_agent: false,
    context_from: "",
    continuity: false,
    enabled_toolsets: [],
    workdir: "",
    scheduleState: { ...DEFAULT_SCHEDULE_STATE },
    repeat: "",
    fallback_models: "",
    silent_notice: true,
    use_soul: true,
    use_user_md: true,
    use_memory: false,
    run_in_chat: true,
    browser: "",
  };
}

function editorFormFromJob(job: CronJob): CronJobEditorState {
  const form = cronJobFormFromJob(job);
  return {
    ...form,
    scheduleState: parseScheduleString(form.schedule),
    repeat: "",
    fallback_models: (job.fallback_models ?? [])
      .map((m) => `${m.provider}:${m.model}`)
      .join(", "),
    silent_notice: job.silent_notice ?? true,
    use_soul: job.use_soul ?? true,
    use_user_md: job.use_user_md ?? true,
    use_memory: job.use_memory ?? false,
    run_in_chat: job.run_in_chat === true,
    browser: job.browser ?? "",
  };
}

/** Build the create/update payload. ``repeat`` is a create-time setting, so
 *  it is only sent when ``includeRepeat`` is set (the create modal). */
function buildCronJobPayloadFromEditor(
  form: CronJobEditorState,
  includeRepeat = false,
): CronJobMutation {
  const {
    scheduleState,
    repeat,
    fallback_models,
    silent_notice,
    use_soul,
    use_user_md,
    use_memory,
    run_in_chat,
    browser,
    ...payloadForm
  } = form;
  const repeatText = repeat.trim();
  return {
    ...buildCronJobPayload({
      ...payloadForm,
      schedule: buildScheduleString(scheduleState),
    }),
    ...(includeRepeat && repeatText ? { repeat: Number(repeatText) } : {}),
    silent_notice,
    use_soul,
    use_user_md,
    use_memory,
    run_in_chat: payloadForm.no_agent ? null : run_in_chat,
    browser: payloadForm.no_agent ? null : browser || "auto",
    fallback_models: splitCronList(fallback_models),
  };
}

function selectOptions(
  current: string,
  options: Array<{ value: string; label: string }>,
) {
  const known = new Set(options.map((option) => option.value));
  return [
    ...options.map((option) => (
      <SelectOption key={option.value} value={option.value}>
        {option.label}
      </SelectOption>
    )),
    ...(current && !known.has(current)
      ? [
          <SelectOption key={current} value={current}>
            {current}
          </SelectOption>,
        ]
      : []),
  ];
}

function CronAdvancedFields({
  idPrefix,
  form,
  onChange,
  modelOptions,
  availableToolsets,
  showRepeat,
}: {
  idPrefix: string;
  form: CronJobEditorState;
  onChange: (form: CronJobEditorState) => void;
  modelOptions: ModelOptionsResult | null;
  availableToolsets: ToolsetInfo[];
  showRepeat?: boolean;
}) {
  const { t } = useI18n();
  const extra = cronExtraLabels(t);
  const update = <K extends keyof CronJobEditorState,>(
    key: K,
    next: CronJobEditorState[K],
  ) => {
    onChange({ ...form, [key]: next });
  };

  const providers = (modelOptions?.providers ?? []).filter(
    (p) => p.authenticated !== false,
  );
  const selectedProvider = providers.find((p) => p.slug === form.provider);
  const models = selectedProvider?.models ?? [];

  return (
    <details className="border border-border bg-background/30 p-3" open>
      <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Advanced fields
      </summary>
      <div className="mt-3 grid gap-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="grid gap-1">
            <Label htmlFor={`${idPrefix}-provider`}>Provider</Label>
            <Select
              id={`${idPrefix}-provider`}
              value={form.provider}
              onValueChange={(v) => {
                onChange({ ...form, provider: v, model: "" });
              }}
            >
              <SelectOption value="">Default</SelectOption>
              {selectOptions(
                form.provider,
                providers.map((p) => ({ value: p.slug, label: p.name })),
              )}
            </Select>
          </div>
          <div className="grid gap-1">
            <Label htmlFor={`${idPrefix}-model`}>Model</Label>
            <Select
              id={`${idPrefix}-model`}
              value={form.model}
              onValueChange={(v) => update("model", v)}
            >
              <SelectOption value="">Default</SelectOption>
              {selectOptions(
                form.model,
                models.map((model) => ({ value: model, label: model })),
              )}
            </Select>
          </div>
        </div>

        <div className="grid gap-1">
          <Label htmlFor={`${idPrefix}-base-url`}>Base URL override</Label>
          <Input
            id={`${idPrefix}-base-url`}
            placeholder="https://api.example.com/v1"
            value={form.base_url}
            onChange={(e) => update("base_url", e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              className="accent-foreground"
              checked={form.no_agent}
              onChange={(e) => update("no_agent", e.target.checked)}
            />
            no_agent: run the script only and deliver stdout verbatim
          </label>
          <div className="grid gap-1">
            <Label htmlFor={`${idPrefix}-script`}>Script</Label>
            <Input
              id={`${idPrefix}-script`}
              value={form.script}
              onChange={(e) => update("script", e.target.value)}
              placeholder="relative/path/in/scripts"
            />
          </div>
        </div>

        <div className="grid gap-1">
          <Label htmlFor={`${idPrefix}-workdir`}>Workdir</Label>
          <Input
            id={`${idPrefix}-workdir`}
            value={form.workdir}
            onChange={(e) => update("workdir", e.target.value)}
            placeholder="/absolute/project/path"
          />
        </div>

        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            className="accent-foreground"
            checked={form.continuity}
            onChange={(e) => update("continuity", e.target.checked)}
          />
          continuity: each run sees the previous run&apos;s output (dedupe, pick up where it left off)
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="grid gap-1">
            <Label htmlFor={`${idPrefix}-context-from`}>context_from job IDs</Label>
            <textarea
              id={`${idPrefix}-context-from`}
              className="flex min-h-[64px] w-full border border-border bg-background/40 px-3 py-2 text-xs font-courier shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30 focus-visible:border-foreground/25"
              placeholder="one job id per line"
              value={form.context_from}
              onChange={(e) => update("context_from", e.target.value)}
            />
          </div>
          <div className="grid gap-1">
            <Label htmlFor={`${idPrefix}-toolsets`}>enabled_toolsets</Label>
            <NameCheckboxPicker
              id={`${idPrefix}-toolsets`}
              available={availableToolsets}
              selected={form.enabled_toolsets}
              onChange={(v) => update("enabled_toolsets", v)}
              emptyLabel="No toolsets available."
            />
          </div>
        </div>

        {showRepeat && (
          <div className="grid gap-1">
            <Label htmlFor={`${idPrefix}-repeat`}>Repeat (optional)</Label>
            <Input
              id={`${idPrefix}-repeat`}
              type="number"
              min={1}
              placeholder="blank = forever, 1 = once"
              value={form.repeat}
              onChange={(e) => update("repeat", e.target.value)}
            />
          </div>
        )}

        <div className="grid gap-1">
          <Label htmlFor={`${idPrefix}-fallback`}>{extra.fallbackModels}</Label>
          <Input
            id={`${idPrefix}-fallback`}
            placeholder="deepseek:deepseek-chat, openai:gpt-4o-mini"
            value={form.fallback_models}
            onChange={(e) => update("fallback_models", e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            {extra.fallbackModelsHint}
          </p>
        </div>

        <div className="grid gap-2">
          <Label>{extra.contextToggles}</Label>
          {(
            [
              ["silent_notice", extra.silentNotice],
              ["use_soul", extra.useSoul],
              ["use_user_md", extra.useUserMd],
              ["use_memory", extra.useMemory],
            ] as const
          ).map(([key, label]) => (
            <label
              key={key}
              className="flex items-center gap-2 text-xs text-muted-foreground"
            >
              <input
                type="checkbox"
                className="accent-foreground"
                checked={form[key]}
                onChange={(e) => update(key, e.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>
    </details>
  );
}

interface CronJobFormFieldsProps {
  idPrefix: string;
  autoFocus?: boolean;
  form: CronJobEditorState;
  resources: CronJobFormResources;
  onChange: (form: CronJobEditorState) => void;
  showRepeat?: boolean;
}

function CronJobFormFields({
  idPrefix,
  autoFocus,
  form,
  resources,
  onChange,
  showRepeat,
}: CronJobFormFieldsProps) {
  const { t } = useI18n();
  const extra = cronExtraLabels(t);
  const { availableSkills, availableToolsets, deliveryTargets, modelOptions } = resources;
  const update = <K extends keyof CronJobEditorState,>(
    key: K,
    next: CronJobEditorState[K],
  ) => {
    onChange({ ...form, [key]: next });
  };
  const onlyLocalAvailable =
    deliveryTargets.filter(
      (target) => target.id !== "local" && target.id !== "origin",
    ).length === 0;

  const deliveryOptions = selectOptions(form.deliver, [
    ...deliveryTargets.map((target) => {
      const base = target.id === "local" ? t.cron.delivery.local : target.name;
      if (target.id !== "local" && !target.home_target_set) {
        const hint = t.cron.delivery.needsHomeChannel ?? "set a home channel first";
        return { value: target.id, label: `${base} — ${hint}` };
      }
      return { value: target.id, label: base };
    }),
  ]);

  return (
    <>
      <div className="grid gap-2">
        <Label htmlFor={`${idPrefix}-name`}>{t.cron.nameOptional}</Label>
        <Input
          id={`${idPrefix}-name`}
          autoFocus={autoFocus}
          placeholder={t.cron.namePlaceholder}
          value={form.name}
          onChange={(e) => update("name", e.target.value)}
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor={`${idPrefix}-prompt`}>{t.cron.prompt}</Label>
        <textarea
          id={`${idPrefix}-prompt`}
          className="flex min-h-[80px] w-full border border-border bg-background/40 px-3 py-2 text-sm font-courier shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30 focus-visible:border-foreground/25"
          placeholder={t.cron.promptPlaceholder}
          value={form.prompt}
          onChange={(e) => update("prompt", e.target.value)}
        />
      </div>

      <ScheduleBuilder
        value={form.scheduleState}
        onChange={(state) => update("scheduleState", state)}
      />

      <div className="grid gap-2">
        <Label htmlFor={`${idPrefix}-deliver`}>{t.cron.deliverTo}</Label>
        <Select
          id={`${idPrefix}-deliver`}
          value={form.deliver}
          onValueChange={(v) => update("deliver", v)}
        >
          {deliveryOptions}
        </Select>
        {onlyLocalAvailable && (
          <p className="text-xs text-muted-foreground">
            {t.cron.delivery.noneConfigured ??
              "No messaging platforms configured. Set one up under Channels to deliver reports."}
          </p>
        )}
        {!form.no_agent && form.deliver !== "local" && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="accent-foreground mt-1"
              checked={form.run_in_chat}
              onChange={(e) => update("run_in_chat", e.target.checked)}
            />
            <span className="grid gap-0.5">
              <span>{extra.runInChat}</span>
              <span className="text-xs text-muted-foreground">{extra.runInChatHint}</span>
            </span>
          </label>
        )}
      </div>

      {!form.no_agent && (
        <div className="grid gap-2">
          <Label htmlFor={`${idPrefix}-browser`}>{extra.browser}</Label>
          <Select
            id={`${idPrefix}-browser`}
            value={form.browser}
            onValueChange={(v) => update("browser", v)}
          >
            <SelectOption value="">{extra.browserAuto}</SelectOption>
            <SelectOption value="my_chrome">{extra.browserMyChrome}</SelectOption>
            <SelectOption value="server">{extra.browserServer}</SelectOption>
          </Select>
          <p className="text-xs text-muted-foreground">{extra.browserHint}</p>
        </div>
      )}

      <div className="grid gap-2">
        <Label htmlFor={`${idPrefix}-skills`}>Skills (optional)</Label>
        <NameCheckboxPicker
          id={`${idPrefix}-skills`}
          available={availableSkills}
          selected={form.skills}
          onChange={(skills) => update("skills", skills)}
          emptyLabel="No skills installed for this profile."
        />
        <p className="text-xs text-muted-foreground">
          Selected skills are loaded before the prompt runs — the cron
          sets when, the skill sets how.
        </p>
      </div>

      <CronAdvancedFields
        idPrefix={`${idPrefix}-advanced`}
        form={form}
        onChange={onChange}
        modelOptions={modelOptions}
        availableToolsets={availableToolsets}
        showRepeat={showRepeat}
      />
    </>
  );
}

/** The dashboard switcher's profile scopes the page; "All profiles" stays one click away. */
function initialCronProfile(): string {
  return getManagementProfile() || "all";
}

/** Where a new job / blueprint / the archive toggle land: the filtered profile, or under
 *  "All profiles" the switcher's one (never silently the default profile). */
function cronTargetProfile(selected: string): string {
  return selected === "all" ? getManagementProfile() || "default" : selected;
}

export default function CronPage() {
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const schedulerStaleAgeS = cronSchedulerStaleAgeS(jobs);
  const [triggeringJobKeys, setTriggeringJobKeys] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const triggerControllerRef = useRef<CronTriggerController | null>(null);

  useEffect(() => {
    const controller = createCronTriggerController((key, running) => {
      if (triggerControllerRef.current !== controller) return;
      setTriggeringJobKeys((current) => {
        const next = new Set(current);
        if (running) next.add(key);
        else next.delete(key);
        return next;
      });
    });
    triggerControllerRef.current = controller;

    return () => {
      triggerControllerRef.current = null;
    };
  }, []);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [selectedProfile, setSelectedProfile] = useState(initialCronProfile);
  const targetProfile = cronTargetProfile(selectedProfile);
  const [view, setView] = useState<"jobs" | "blueprints">("jobs");
  const [viewMode, setViewMode] = useState<"list" | "calendar">("list");
  const [loading, setLoading] = useState(true);
  const { toast, showToast } = useToast();
  const { t, locale } = useI18n();
  const { setEnd } = usePageHeader();
  const cronExtra = cronExtraLabels(t);

  const [archiveChats, toggleArchiveChats] = useCronArchiveChats(
    targetProfile,
    useCallback((message: string) => showToast(message, "error"), [showToast]),
  );

  // Translation surface for the human-readable schedule describer.
  // English ordinals are a special case ("1st", "2nd", "23rd"); every
  // other locale falls back to the plain numeric form, which avoids
  // shipping incorrect grammar (e.g. naive "1th"/"2th" suffixes that
  // don't exist in most languages).
  //
  // Built inline (not memoized) — the cron page renders a small job
  // list, this is single-digit microseconds, and a useMemo here would
  // just add boilerplate.
  const scheduleDescribeStrings: ScheduleDescribeStrings = {
    ...t.cron.scheduleDescribe,
    weekdaysShort: t.cron.scheduleModes.weekdaysShort,
    ordinal: locale === "en" ? englishOrdinal : (n: number) => String(n),
  };

  // New job modal state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createProfile, setCreateProfile] = useState("default");
  const [createForm, setCreateForm] = useState<CronJobEditorState>(
    emptyCronJobForm,
  );
  const closeCreateModal = useCallback(() => setCreateModalOpen(false), []);
  const createModalRef = useModalBehavior({
    open: createModalOpen,
    onClose: closeCreateModal,
  });
  const [deliveryTargets, setDeliveryTargets] = useState<CronDeliveryTarget[]>([
    { id: "local", name: "Local", home_target_set: true, home_env_var: null },
  ]);
  const [creating, setCreating] = useState(false);

  // Edit job modal state
  const [editJob, setEditJob] = useState<CronJob | null>(null);
  const [editForm, setEditForm] = useState<CronJobEditorState>(
    emptyCronJobForm,
  );
  const [saving, setSaving] = useState(false);
  const closeEditModal = useCallback(() => setEditJob(null), []);
  const editModalRef = useModalBehavior({
    open: editJob !== null,
    onClose: closeEditModal,
  });

  // Skills installed in the profile a job will run under, for the
  // attach-skill selector (parity with `clawk cron edit --add-skill`).
  // Keyed on the create-modal profile; the edit modal reuses the list —
  // a job's current skills are always shown even if not in it.
  const [availableSkills, setAvailableSkills] = useState<SkillInfo[]>([]);
  const [availableToolsets, setAvailableToolsets] = useState<ToolsetInfo[]>([]);
  const [modelOptions, setModelOptions] = useState<ModelOptionsResult | null>(null);

  const resourceProfile = editJob ? getJobProfile(editJob) : createProfile;

  const openEditModal = useCallback((job: CronJob) => {
    setEditJob(job);
    setEditForm(editorFormFromJob(job));
  }, []);

  const selectedProfileRef = useRef(selectedProfile);
  const jobsRequestGenerationRef = useRef(0);
  const jobsActiveRef = useRef(false);
  // Humanized error from the last GET /api/cron/jobs failure; renders a
  // persistent Retry notice instead of a vanishing toast.
  const [jobsLoadError, setJobsLoadError] = useState<string | null>(null);

  const loadJobs = useCallback((profile: string) => {
    if (!jobsActiveRef.current || selectedProfileRef.current !== profile) return;

    const generation = ++jobsRequestGenerationRef.current;

    api
      .getCronJobs(profile)
      .then((nextJobs) => {
        if (
          jobsRequestGenerationRef.current === generation &&
          selectedProfileRef.current === profile
        ) {
          setJobs(nextJobs);
          setJobsLoadError(null);
        }
      })
      .catch((e: unknown) => {
        if (
          jobsRequestGenerationRef.current === generation &&
          selectedProfileRef.current === profile
        ) {
          setJobsLoadError(errorMessage(e));
        }
      })
      .finally(() => {
        if (
          jobsRequestGenerationRef.current === generation &&
          selectedProfileRef.current === profile
        ) setLoading(false);
      });
  }, []);

  useEffect(() => {
    api
      .getProfiles()
      .then((res) => setProfiles(res.profiles))
      .catch(() => setProfiles([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .getCronDeliveryTargets(resourceProfile)
      .then((res) => {
        if (!cancelled) setDeliveryTargets(res.targets);
      })
      .catch(() => {
        // Fall back to local-only so the modal still works if the endpoint fails.
        if (!cancelled) {
          setDeliveryTargets([
            { id: "local", name: "Local", home_target_set: true, home_env_var: null },
          ]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [resourceProfile]);

  useEffect(() => {
    jobsActiveRef.current = true;
    selectedProfileRef.current = selectedProfile;
    loadJobs(selectedProfile);

    return () => {
      jobsActiveRef.current = false;
      jobsRequestGenerationRef.current += 1;
    };
  }, [loadJobs, selectedProfile]);

  // Load resources from the profile the create/edit form actually targets.
  // Pass "default" explicitly so the global dashboard profile switch cannot
  // redirect a default-profile cron form to some other profile.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.getSkills(resourceProfile).catch(() => []),
      api.getToolsets(resourceProfile).catch(() => []),
      api.getModelOptions(resourceProfile).catch(() => null),
    ]).then(([skills, toolsets, options]) => {
      if (cancelled) return;
      setAvailableSkills([...skills].sort((a, b) => a.name.localeCompare(b.name)));
      setAvailableToolsets([...toolsets].sort((a, b) => a.name.localeCompare(b.name)));
      setModelOptions(options);
    });
    return () => {
      cancelled = true;
    };
  }, [resourceProfile]);

  const handleCreate = async () => {
    const repeatText = createForm.repeat.trim();
    if (repeatText) {
      const repeatNum = Number(repeatText);
      if (!Number.isInteger(repeatNum) || repeatNum < 1) {
        showToast("Repeat must be a positive whole number", "error");
        focusCronField("cron-advanced-repeat");
        return;
      }
    }
    const payload = buildCronJobPayloadFromEditor(createForm, true);
    if (
      !payload.schedule ||
      (!payload.no_agent && !cronJobHasExecutionContent(payload))
    ) {
      showToast(`${t.cron.prompt} & ${t.cron.schedule} required`, "error");
      return;
    }
    if (payload.no_agent && !payload.script) {
      showToast(t.cron.scriptRequired ?? en.cron.scriptRequired!, "error");
      focusCronField("cron-script");
      return;
    }
    setCreating(true);
    try {
      await api.createCronJob(payload, createProfile);
      showToast(t.common.create + " ✓", "success");
      setCreateForm(emptyCronJobForm());
      setCreateModalOpen(false);
      loadJobs(selectedProfile);
    } catch (e) {
      showToast(`${t.config.failedToSave}: ${errorMessage(e)}`, "error");
    } finally {
      setCreating(false);
    }
  };

  const handleEdit = async () => {
    if (!editJob) return;
    const payload = buildCronJobPayloadFromEditor(editForm);
    if (
      !payload.schedule ||
      (!payload.no_agent && !cronJobHasExecutionContent(payload))
    ) {
      showToast(`${t.cron.prompt} & ${t.cron.schedule} required`, "error");
      return;
    }
    if (payload.no_agent && !payload.script) {
      showToast(t.cron.scriptRequired ?? en.cron.scriptRequired!, "error");
      focusCronField("edit-cron-script");
      return;
    }
    setSaving(true);
    try {
      await api.updateCronJob(
        editJob.id,
        payload,
        getJobProfile(editJob),
      );
      showToast("Saved changes ✓", "success");
      setEditJob(null);
      loadJobs(selectedProfile);
    } catch (e) {
      showToast(`${t.config.failedToSave}: ${errorMessage(e)}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const handlePauseResume = async (job: CronJob) => {
    try {
      const isPaused = getJobState(job) === "paused";
      const profile = getJobProfile(job);
      const jobKey = getJobKey(job);
      const updatedJob = isPaused
        ? await api.resumeCronJob(job.id, profile)
        : await api.pauseCronJob(job.id, profile);
      showToast(
        `${isPaused ? t.cron.resume : t.cron.pause}: "${truncateText(getJobTitle(job), 30)}"`,
        "success",
      );
      // Apply the API's updated job instead of reloading right away: an
      // immediate reload could read stale data before the change propagated.
      // Keep the listing's profile identity so the job key stays stable.
      setJobs((prev) =>
        prev.map((j) =>
          getJobKey(j) === jobKey
            ? { ...j, ...updatedJob, profile: j.profile, profile_name: j.profile_name }
            : j,
        ),
      );
    } catch (e) {
      showToast(`${t.status.error}: ${errorMessage(e)}`, "error");
      // On failure, resync with the backend so the list doesn't drift.
      loadJobs(selectedProfile);
    }
  };

  const handleTrigger = async (job: CronJob) => {
    const jobKey = getJobKey(job);
    const label = `${t.cron.triggerNow}: "${truncateText(getJobTitle(job), 30)}"`;
    const viewProfile = selectedProfile;
    const controller = triggerControllerRef.current;

    if (!controller) return;

    try {
      // No pre-request toast: the controller's running state already gives
      // immediate in-progress feedback (disabled + spinning action), and a
      // success-styled toast before the HTTP response would claim a result
      // the request has not produced yet. Terminal feedback only.
      const result = await controller.run(
        jobKey,
        () => api.triggerCronJob(job.id, getJobProfile(job)),
      );

      if (
        triggerControllerRef.current !== controller ||
        selectedProfileRef.current !== viewProfile ||
        !result.started
      ) return;

      showToast(`${label} ✓`, "success");
      loadJobs(viewProfile);
    } catch (e) {
      if (
        triggerControllerRef.current === controller &&
        selectedProfileRef.current === viewProfile
      ) {
        showToast(`${t.status.error}: ${errorMessage(e)}`, "error");
      }
    }
  };

  const jobDelete = useConfirmDelete({
    onDelete: useCallback(
      async (key: string) => {
        const { profile, id } = splitJobKey(key);
        const job = jobs.find((j) => getJobKey(j) === key);
        try {
          await api.deleteCronJob(id, profile);
          showToast(
            `${t.common.delete}: "${job ? truncateText(getJobTitle(job), 30) : id}"`,
            "success",
          );
          loadJobs(selectedProfile);
        } catch (e) {
          showToast(`${t.status.error}: ${errorMessage(e)}`, "error");
          throw e;
        }
      },
      [jobs, loadJobs, selectedProfile, showToast, t.common.delete, t.status.error],
    ),
  });

  // Put "Create" button in page header
  useLayoutEffect(() => {
    setEnd(
      <Button
        className="uppercase"
        size="sm"
        onClick={() => {
          setCreateProfile(targetProfile);
          setCreateModalOpen(true);
        }}
      >
        {t.common.create}
      </Button>,
    );
    return () => {
      setEnd(null);
    };
  }, [setEnd, t.common.create, loading, targetProfile]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner className="text-2xl text-primary" />
      </div>
    );
  }

  const pendingJob = jobDelete.pendingId
    ? jobs.find((j) => getJobKey(j) === jobDelete.pendingId)
    : null;

  return (
    <div className="flex flex-col gap-6">
      <PluginSlot name="cron:top" />
      <Toast toast={toast} />

      {jobsLoadError && (
        <LoadErrorNotice
          what={t.cron.loadWhat ?? en.cron.loadWhat!}
          detail={jobsLoadError}
          onRetry={() => loadJobs(selectedProfile)}
        />
      )}

      {schedulerStaleAgeS !== null && (
        <p className="text-sm text-warning font-medium" data-testid="cron-scheduler-stale">
          {(t.cron.schedulerLastTicked ?? en.cron.schedulerLastTicked!).replace(
            "{when}",
            cronAgoLabel(schedulerStaleAgeS),
          )}
        </p>
      )}

      <Segmented
        value={view}
        onChange={(v) => setView(v as "jobs" | "blueprints")}
        options={[
          { value: "jobs", label: "Jobs" },
          { value: "blueprints", label: "Blueprints" },
        ]}
      />

      {view === "blueprints" && (
        <AutomationBlueprints
          profile={targetProfile}
          onCreated={() => loadJobs(selectedProfile)}
        />
      )}


      <DeleteConfirmDialog
        open={jobDelete.isOpen}
        onCancel={jobDelete.cancel}
        onConfirm={jobDelete.confirm}
        title={t.cron.confirmDeleteTitle}
        description={
          pendingJob
            ? `"${truncateText(getJobTitle(pendingJob), 40)}" — ${
                t.cron.confirmDeleteMessage
              }`
            : t.cron.confirmDeleteMessage
        }
        loading={jobDelete.isDeleting}
      />

      {/* Create job modal */}
      {createModalOpen && (
        <div
          ref={createModalRef}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 p-4"
          onClick={(e) => e.target === e.currentTarget && setCreateModalOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-cron-title"
        >
          <div className={cn(themedBody, "relative w-full max-w-3xl max-h-[90vh] border border-border bg-card shadow-2xl flex flex-col")}>
            <Button
              ghost
              size="icon"
              onClick={() => setCreateModalOpen(false)}
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              aria-label="Close"
            >
              <X />
            </Button>

            <header className="p-5 pb-3 border-b border-border">
              <h2
                id="create-cron-title"
                className="font-mondwest text-display text-base tracking-wider"
              >
                {t.cron.newJob}
              </h2>
            </header>

            <div className="min-h-0 overflow-y-auto p-5 grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="cron-profile">Profile</Label>
                <Select
                  id="cron-profile"
                  value={createProfile}
                  onValueChange={(v) => setCreateProfile(v)}
                >
                  {profiles.map((profile) => (
                    <SelectOption key={profile.name} value={profile.name}>
                      {profile.name}
                    </SelectOption>
                  ))}
                </Select>
              </div>

              <CronJobFormFields
                idPrefix="cron"
                autoFocus
                showRepeat
                form={createForm}
                onChange={setCreateForm}
                resources={{
                  availableSkills,
                  availableToolsets,
                  modelOptions,
                  deliveryTargets,
                }}
              />

              <div className="flex justify-end">
                <Button
                  className="uppercase"
                  size="sm"
                  onClick={handleCreate}
                  disabled={creating}
                  prefix={creating ? <Spinner /> : undefined}
                >
                  {creating ? t.common.creating : t.common.create}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit job modal */}
      {editJob && (
        <div
          ref={editModalRef}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 p-4"
          onClick={(e) => e.target === e.currentTarget && setEditJob(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-cron-title"
        >
          <div className={cn(themedBody, "relative w-full max-w-3xl max-h-[90vh] border border-border bg-card shadow-2xl flex flex-col")}>
            <Button
              ghost
              size="icon"
              onClick={() => setEditJob(null)}
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              aria-label="Close"
            >
              <X />
            </Button>

            <header className="p-5 pb-3 border-b border-border">
              <h2
                id="edit-cron-title"
                className="font-mondwest text-display text-base tracking-wider"
              >
                Edit job
              </h2>
            </header>

            <div className="min-h-0 overflow-y-auto p-5 grid gap-4">
              <CronJobFormFields
                idPrefix="edit-cron"
                autoFocus
                form={editForm}
                onChange={setEditForm}
                resources={{
                  availableSkills,
                  availableToolsets,
                  modelOptions,
                  deliveryTargets,
                }}
              />

              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground font-mono-ui truncate pr-4">
                  {editJob.id}
                </span>
                <Button
                  className="uppercase"
                  size="sm"
                  onClick={handleEdit}
                  disabled={saving}
                  prefix={saving ? <Spinner /> : undefined}
                >
                  {saving ? t.common.loading : "Save changes"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {view === "jobs" && (
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <H2
            variant="sm"
            className="flex items-center gap-2 text-muted-foreground"
          >
            <Clock className="h-4 w-4" />
            {t.cron.scheduledJobs} ({jobs.length})
          </H2>

          <div className="flex flex-wrap items-end gap-3">
            <div className="grid gap-1">
              <Label>{cronExtra.viewLabel}</Label>
              <div className="inline-flex border border-border">
                <button
                  type="button"
                  onClick={() => setViewMode("list")}
                  className={cn(
                    "h-9 px-3 text-xs uppercase tracking-wide transition-colors",
                    viewMode === "list"
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {cronExtra.listView}
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("calendar")}
                  className={cn(
                    "h-9 border-l border-border px-3 text-xs uppercase tracking-wide transition-colors",
                    viewMode === "calendar"
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {cronExtra.calendarView}
                </button>
              </div>
            </div>
            <div className="grid gap-1 min-w-[220px]">
              <Label htmlFor="cron-profile-filter">Profile</Label>
              <Select
                id="cron-profile-filter"
                value={selectedProfile}
                onValueChange={(v) => setSelectedProfile(v)}
              >
                <SelectOption value="all">All profiles</SelectOption>
                {profiles.map((profile) => (
                  <SelectOption key={profile.name} value={profile.name}>
                    {profile.name}
                  </SelectOption>
                ))}
              </Select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="cron-archive-chats" title={`${cronExtra.archiveChatsHint} (${targetProfile})`}>
                {cronExtra.archiveChats}
              </Label>
              <div
                className="flex h-9 items-center"
                title={cronExtra.archiveChatsHint}
              >
                <Switch
                  id="cron-archive-chats"
                  checked={archiveChats === true}
                  disabled={archiveChats === null}
                  onCheckedChange={toggleArchiveChats}
                />
              </div>
            </div>
          </div>
        </div>

        {viewMode === "calendar" && (
          <CronCalendar profile={selectedProfile} />
        )}

        {viewMode === "list" && jobs.length === 0 && !jobsLoadError && (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 py-8 text-center text-sm text-muted-foreground">
              <span>{t.cron.noJobs}</span>
              <Button
                className="uppercase"
                size="sm"
                onClick={() => {
                  setCreateProfile(targetProfile);
                  setCreateModalOpen(true);
                }}
              >
                {t.common.create}
              </Button>
            </CardContent>
          </Card>
        )}

        {viewMode === "list" &&
          jobs.map((job) => (
            <CronJobCard
              key={getJobKey(job)}
              job={job}
              scheduleStrings={scheduleDescribeStrings}
              triggering={triggeringJobKeys.has(getJobKey(job))}
              onPauseResume={(j) => void handlePauseResume(j)}
              onTrigger={(j) => void handleTrigger(j)}
              onEdit={openEditModal}
              onDelete={(j) => jobDelete.requestDelete(getJobKey(j))}
            />
          ))}
      </div>
      )}

      <PluginSlot name="cron:bottom" />
    </div>
  );
}
