import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { Clock, Pause, Pencil, Play, Trash2, X, Zap } from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Select, SelectOption } from "@nous-research/ui/ui/components/select";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { H2 } from "@nous-research/ui/ui/components/typography/h2";
import { api } from "@/lib/api";
import type { CronJob, ProfileInfo } from "@/lib/api";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { CronCalendar } from "@/components/CronCalendar";
import {
  DEFAULT_SCHEDULE_STATE,
  ScheduleBuilder,
} from "@/components/ScheduleBuilder";
import {
  buildScheduleString,
  describeSchedule,
  englishOrdinal,
  type ScheduleBuilderState,
  type ScheduleDescribeStrings,
} from "@/lib/schedule";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { useConfirmDelete } from "@nous-research/ui/hooks/use-confirm-delete";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { PluginSlot } from "@/plugins";
import { cn, themedBody } from "@/lib/utils";

function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function truncateText(value: string, maxLength: number): string {
  return value.length > maxLength
    ? value.slice(0, maxLength) + "..."
    : value;
}

function getJobPrompt(job: CronJob): string {
  return asText(job.prompt);
}

function getJobName(job: CronJob): string {
  return asText(job.name).trim();
}

function getJobTitle(job: CronJob): string {
  const name = getJobName(job);
  if (name) return name;

  const prompt = getJobPrompt(job);
  if (prompt) return truncateText(prompt, 60);

  const script = asText(job.script);
  if (script) return truncateText(script, 60);

  return job.id || "Cron job";
}

function getJobScheduleDisplay(
  job: CronJob,
  strings: ScheduleDescribeStrings,
): string {
  // Prefer a structured render so cron expressions like
  // ``30 14 * * 1,3,5`` surface as "Weekly on Mon, Wed, Fri at 14:30"
  // in the list instead of the raw five-field gibberish. Falls back
  // through the existing chain (``schedule_display`` from the backend,
  // then the structured ``display`` field, then the raw ``expr``) so
  // legacy job rows still render *something* meaningful.
  return describeSchedule(
    job.schedule,
    asText(job.schedule_display) || asText(job.schedule?.display),
    strings,
  );
}

function getJobState(job: CronJob): string {
  return asText(job.state) || (job.enabled === false ? "disabled" : "scheduled");
}

function getJobProfile(job: CronJob): string {
  return asText(job.profile) || asText(job.profile_name) || "default";
}

function getJobKey(job: CronJob): string {
  return `${getJobProfile(job)}:${job.id}`;
}

function splitJobKey(key: string): { profile: string; id: string } {
  const idx = key.indexOf(":");
  if (idx === -1) return { profile: "default", id: key };
  return { profile: key.slice(0, idx) || "default", id: key.slice(idx + 1) };
}

function profileLabel(profile: string): string {
  return profile === "default" ? "default" : profile;
}

const STATUS_TONE: Record<string, "success" | "warning" | "destructive"> = {
  enabled: "success",
  scheduled: "success",
  paused: "warning",
  error: "destructive",
  completed: "destructive",
};

export default function CronPage() {
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [selectedProfile, setSelectedProfile] = useState("all");
  const [viewMode, setViewMode] = useState<"list" | "calendar">("list");
  const [loading, setLoading] = useState(true);
  const { toast, showToast } = useToast();
  const { t, locale } = useI18n();
  // New cron labels are optional in non-eager locales, so fall back to English.
  const cronExtra = {
    silentNotice: t.cron.silentNotice ?? "Notify even when there's nothing new",
    useSoul: t.cron.useSoul ?? "Use SOUL.md (assistant identity)",
    useUserMd: t.cron.useUserMd ?? "Use USER.md (user profile)",
    useMemory: t.cron.useMemory ?? "Use MEMORY.md (long-term memory)",
    contextToggles: t.cron.contextToggles ?? "Context & delivery",
    fallbackModels: t.cron.fallbackModels ?? "Fallback models (optional)",
    fallbackModelsHint:
      t.cron.fallbackModelsHint ??
      "If the primary model fails, retry with these. Format provider:model, comma-separated.",
    viewLabel: t.cron.viewLabel ?? "View",
    listView: t.cron.listView ?? "List",
    calendarView: t.cron.calendarView ?? "Calendar",
  };
  const { setEnd } = usePageHeader();

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
  const [prompt, setPrompt] = useState("");
  // The schedule is now constructed via the ScheduleBuilder; we keep
  // the full builder state so flipping between modes during edit
  // doesn't erase the user's intermediate inputs. The actual string
  // sent to the backend is derived via ``buildScheduleString`` at
  // submit time.
  const [scheduleState, setScheduleState] = useState<ScheduleBuilderState>(
    DEFAULT_SCHEDULE_STATE,
  );
  const [name, setName] = useState("");
  const closeCreateModal = useCallback(() => setCreateModalOpen(false), []);
  const createModalRef = useModalBehavior({
    open: createModalOpen,
    onClose: closeCreateModal,
  });
  const [deliver, setDeliver] = useState("local");
  const [creating, setCreating] = useState(false);
  // Advanced create fields (collapsed by default)
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [model, setModel] = useState("");
  const [provider, setProvider] = useState("");
  const [skills, setSkills] = useState("");
  const [repeat, setRepeat] = useState("");
  const [script, setScript] = useState("");
  const [noAgent, setNoAgent] = useState(false);
  const [contextFrom, setContextFrom] = useState("");
  const [enabledToolsets, setEnabledToolsets] = useState("");
  const [workdir, setWorkdir] = useState("");
  // Per-cron behaviour toggles (advanced).
  const [silentNotice, setSilentNotice] = useState(true);
  const [useSoul, setUseSoul] = useState(true);
  const [useUserMd, setUseUserMd] = useState(true);
  const [useMemory, setUseMemory] = useState(false);
  const [fallbackModels, setFallbackModels] = useState("");
  const createProfile = selectedProfile === "all" ? "default" : selectedProfile;

  // Edit job modal state
  const [editJob, setEditJob] = useState<CronJob | null>(null);
  const [editPrompt, setEditPrompt] = useState("");
  const [editSchedule, setEditSchedule] = useState("");
  const [editName, setEditName] = useState("");
  const [editDeliver, setEditDeliver] = useState("local");
  const [editSilentNotice, setEditSilentNotice] = useState(true);
  const [editUseSoul, setEditUseSoul] = useState(true);
  const [editUseUserMd, setEditUseUserMd] = useState(true);
  const [editUseMemory, setEditUseMemory] = useState(false);
  const [editFallback, setEditFallback] = useState("");
  const [saving, setSaving] = useState(false);
  const closeEditModal = useCallback(() => setEditJob(null), []);
  const editModalRef = useModalBehavior({
    open: editJob !== null,
    onClose: closeEditModal,
  });

  const openEditModal = useCallback((job: CronJob) => {
    setEditJob(job);
    setEditPrompt(getJobPrompt(job));
    setEditSchedule(
      asText(job.schedule?.expr) || asText(job.schedule_display) || "",
    );
    setEditName(getJobName(job));
    setEditDeliver(asText(job.deliver) || "local");
    setEditSilentNotice(job.silent_notice ?? true);
    setEditUseSoul(job.use_soul ?? true);
    setEditUseUserMd(job.use_user_md ?? true);
    setEditUseMemory(job.use_memory ?? false);
    setEditFallback(
      (job.fallback_models ?? [])
        .map((m) => `${m.provider}:${m.model}`)
        .join(", "),
    );
  }, []);

  const loadJobs = useCallback(() => {
    api
      .getCronJobs(selectedProfile)
      .then(setJobs)
      .catch(() => showToast(t.common.loading, "error"))
      .finally(() => setLoading(false));
  }, [selectedProfile, showToast, t.common.loading]);

  useEffect(() => {
    api
      .getProfiles()
      .then((res) => setProfiles(res.profiles))
      .catch(() => setProfiles([]));
  }, []);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const scheduleString = buildScheduleString(scheduleState);

  const handleCreate = async () => {
    const csv = (s: string) =>
      s
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
    const skillsList = csv(skills);
    const contextList = csv(contextFrom);
    const toolsetsList = csv(enabledToolsets);
    const repeatNum = repeat.trim() ? Number(repeat.trim()) : null;
    if (!scheduleString) {
      showToast(`${t.cron.schedule} required`, "error");
      return;
    }
    // A normal agent job needs a prompt; a no-agent script job runs the
    // script directly, so the prompt is optional in that case.
    if (!prompt.trim() && !(noAgent && script.trim())) {
      showToast(`${t.cron.prompt} required`, "error");
      return;
    }
    if (noAgent && !script.trim()) {
      showToast("No-agent jobs need a script to run", "error");
      return;
    }
    if (repeatNum !== null && (!Number.isInteger(repeatNum) || repeatNum < 1)) {
      showToast("Repeat must be a positive whole number", "error");
      return;
    }
    setCreating(true);
    try {
      await api.createCronJob(
        {
          prompt: prompt.trim() || undefined,
          schedule: scheduleString,
          name: name.trim() || undefined,
          deliver,
          repeat: repeatNum,
          skills: skillsList.length ? skillsList : undefined,
          model: model.trim() || undefined,
          provider: provider.trim() || undefined,
          script: script.trim() || undefined,
          context_from: contextList.length ? contextList : undefined,
          enabled_toolsets: toolsetsList.length ? toolsetsList : undefined,
          workdir: workdir.trim() || undefined,
          no_agent: noAgent || undefined,
          silent_notice: silentNotice,
          use_soul: useSoul,
          use_user_md: useUserMd,
          use_memory: useMemory,
          fallback_models: fallbackModels.trim()
            ? fallbackModels
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            : undefined,
        },
        createProfile,
      );
      showToast(t.common.create + " ✓", "success");
      setPrompt("");
      setScheduleState(DEFAULT_SCHEDULE_STATE);
      setName("");
      setDeliver("local");
      setModel("");
      setProvider("");
      setSkills("");
      setRepeat("");
      setScript("");
      setNoAgent(false);
      setContextFrom("");
      setEnabledToolsets("");
      setWorkdir("");
      setSilentNotice(true);
      setUseSoul(true);
      setUseUserMd(true);
      setUseMemory(false);
      setFallbackModels("");
      setShowAdvanced(false);
      setCreateModalOpen(false);
      loadJobs();
    } catch (e) {
      showToast(`${t.config.failedToSave}: ${e}`, "error");
    } finally {
      setCreating(false);
    }
  };

  const handleEdit = async () => {
    if (!editJob) return;
    if (!editPrompt.trim() || !editSchedule.trim()) {
      showToast(`${t.cron.prompt} & ${t.cron.schedule} required`, "error");
      return;
    }
    setSaving(true);
    try {
      await api.updateCronJob(
        editJob.id,
        {
          prompt: editPrompt.trim(),
          schedule: editSchedule.trim(),
          name: editName.trim(),
          deliver: editDeliver,
          silent_notice: editSilentNotice,
          use_soul: editUseSoul,
          use_user_md: editUseUserMd,
          use_memory: editUseMemory,
          fallback_models: editFallback.trim()
            ? editFallback
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            : [],
        },
        getJobProfile(editJob),
      );
      showToast("Saved changes ✓", "success");
      setEditJob(null);
      loadJobs();
    } catch (e) {
      showToast(`${t.config.failedToSave}: ${e}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const handlePauseResume = async (job: CronJob) => {
    try {
      const isPaused = getJobState(job) === "paused";
      const profile = getJobProfile(job);
      // Bug #29 fix: usar la respuesta del API para actualizar el estado local.
      // Antes hacíamos loadJobs() inmediatamente después de pause/resume, lo que
      // podía leer data stale del backend antes que el cambio se propagara.
      // Ahora el API devuelve el CronJob actualizado y reemplazamos solo ese.
      const updatedJob = isPaused
        ? await api.resumeCronJob(job.id, profile)
        : await api.pauseCronJob(job.id, profile);
      showToast(
        `${isPaused ? t.cron.resume : t.cron.pause}: "${truncateText(getJobTitle(job), 30)}"`,
        "success",
      );
      // Reemplazar solo el job afectado en el estado local — sin race condition
      setJobs((prev) =>
        prev.map((j) => (j.id === updatedJob.id ? updatedJob : j)),
      );
    } catch (e) {
      showToast(`${t.status.error}: ${e}`, "error");
      // Si falló, sincronizar con el backend para no quedar fuera de sync
      loadJobs();
    }
  };

  const handleTrigger = async (job: CronJob) => {
    try {
      await api.triggerCronJob(job.id, getJobProfile(job));
      showToast(
        `${t.cron.triggerNow}: "${truncateText(getJobTitle(job), 30)}"`,
        "success",
      );
      loadJobs();
    } catch (e) {
      showToast(`${t.status.error}: ${e}`, "error");
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
          loadJobs();
        } catch (e) {
          showToast(`${t.status.error}: ${e}`, "error");
          throw e;
        }
      },
      [jobs, loadJobs, showToast, t.common.delete, t.status.error],
    ),
  });

  // Put "Create" button in page header
  useLayoutEffect(() => {
    setEnd(
      <Button
        className="uppercase"
        size="sm"
        onClick={() => setCreateModalOpen(true)}
      >
        {t.common.create}
      </Button>,
    );
    return () => {
      setEnd(null);
    };
  }, [setEnd, t.common.create, loading]);

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
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4"
          onClick={(e) => e.target === e.currentTarget && setCreateModalOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-cron-title"
        >
          <div className={cn(themedBody, "relative w-full max-w-lg max-h-[90vh] border border-border bg-card shadow-2xl flex flex-col")}>
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

            <div className="p-5 grid gap-4 overflow-y-auto flex-1 min-h-0">
              <div className="grid gap-2">
                <Label htmlFor="cron-profile">Profile</Label>
                <Select
                  id="cron-profile"
                  value={createProfile}
                  onValueChange={(v) => setSelectedProfile(v)}
                >
                  {profiles.map((profile) => (
                    <SelectOption key={profile.name} value={profile.name}>
                      {profileLabel(profile.name)}
                    </SelectOption>
                  ))}
                </Select>
              </div>

              <div className="grid gap-2">
                <Label htmlFor="cron-name">{t.cron.nameOptional}</Label>
                <Input
                  id="cron-name"
                  autoFocus
                  placeholder={t.cron.namePlaceholder}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="cron-prompt">{t.cron.prompt}</Label>
                <textarea
                  id="cron-prompt"
                  className="flex min-h-[80px] w-full border border-border bg-background/40 px-3 py-2 text-sm font-courier shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30 focus-visible:border-foreground/25"
                  placeholder={t.cron.promptPlaceholder}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                />
              </div>

              <ScheduleBuilder
                value={scheduleState}
                onChange={setScheduleState}
              />

              <div className="grid gap-2">
                <Label htmlFor="cron-deliver">{t.cron.deliverTo}</Label>
                <Select
                  id="cron-deliver"
                  value={deliver}
                  onValueChange={(v) => setDeliver(v)}
                >
                  <SelectOption value="local">
                    {t.cron.delivery.local}
                  </SelectOption>
                  <SelectOption value="telegram">
                    {t.cron.delivery.telegram}
                  </SelectOption>
                  <SelectOption value="discord">
                    {t.cron.delivery.discord}
                  </SelectOption>
                  <SelectOption value="slack">
                    {t.cron.delivery.slack}
                  </SelectOption>
                  <SelectOption value="email">
                    {t.cron.delivery.email}
                  </SelectOption>
                  <SelectOption value="origin">
                    Origin (reply where created)
                  </SelectOption>
                </Select>
              </div>

              <div className="grid gap-2">
                <button
                  type="button"
                  onClick={() => setShowAdvanced((v) => !v)}
                  className="flex items-center gap-1 self-start text-xs uppercase tracking-wide text-muted-foreground hover:text-foreground"
                >
                  {showAdvanced ? "▾ Advanced" : "▸ Advanced"}
                </button>
                {showAdvanced && (
                  <div className="grid gap-3 border-l border-border pl-3">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="grid gap-1.5">
                        <Label htmlFor="cron-model">Model (optional)</Label>
                        <Input
                          id="cron-model"
                          placeholder="e.g. claude-opus-4-8"
                          value={model}
                          onChange={(e) => setModel(e.target.value)}
                        />
                      </div>
                      <div className="grid gap-1.5">
                        <Label htmlFor="cron-provider">Provider (optional)</Label>
                        <Input
                          id="cron-provider"
                          placeholder="e.g. anthropic"
                          value={provider}
                          onChange={(e) => setProvider(e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor="cron-skills">Skills (optional)</Label>
                      <Input
                        id="cron-skills"
                        placeholder="comma-separated skills to load"
                        value={skills}
                        onChange={(e) => setSkills(e.target.value)}
                      />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="grid gap-1.5">
                        <Label htmlFor="cron-repeat">Repeat (optional)</Label>
                        <Input
                          id="cron-repeat"
                          type="number"
                          min={1}
                          placeholder="blank = forever, 1 = once"
                          value={repeat}
                          onChange={(e) => setRepeat(e.target.value)}
                        />
                      </div>
                      <div className="grid gap-1.5">
                        <Label htmlFor="cron-workdir">Working dir (optional)</Label>
                        <Input
                          id="cron-workdir"
                          placeholder="run from this directory"
                          value={workdir}
                          onChange={(e) => setWorkdir(e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor="cron-script">Script (optional)</Label>
                      <Input
                        id="cron-script"
                        placeholder="script under ~/.clawksis/scripts/ (.sh or .py)"
                        value={script}
                        onChange={(e) => setScript(e.target.value)}
                      />
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={noAgent}
                          onChange={(e) => setNoAgent(e.target.checked)}
                        />
                        No-agent: run the script directly (its output is the result)
                      </label>
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor="cron-context-from">
                        Context from (optional)
                      </Label>
                      <Input
                        id="cron-context-from"
                        placeholder="comma-separated job IDs to chain output from"
                        value={contextFrom}
                        onChange={(e) => setContextFrom(e.target.value)}
                      />
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor="cron-toolsets">
                        Enabled toolsets (optional)
                      </Label>
                      <Input
                        id="cron-toolsets"
                        placeholder="comma-separated toolsets (e.g. web, search)"
                        value={enabledToolsets}
                        onChange={(e) => setEnabledToolsets(e.target.value)}
                      />
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor="cron-fallback">
                        {cronExtra.fallbackModels}
                      </Label>
                      <Input
                        id="cron-fallback"
                        placeholder="deepseek:deepseek-chat, openai:gpt-4o-mini"
                        value={fallbackModels}
                        onChange={(e) => setFallbackModels(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">
                        {cronExtra.fallbackModelsHint}
                      </p>
                    </div>
                    <div className="grid gap-2">
                      <Label>{cronExtra.contextToggles}</Label>
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={silentNotice}
                          onChange={(e) => setSilentNotice(e.target.checked)}
                        />
                        {cronExtra.silentNotice}
                      </label>
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={useSoul}
                          onChange={(e) => setUseSoul(e.target.checked)}
                        />
                        {cronExtra.useSoul}
                      </label>
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={useUserMd}
                          onChange={(e) => setUseUserMd(e.target.checked)}
                        />
                        {cronExtra.useUserMd}
                      </label>
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={useMemory}
                          onChange={(e) => setUseMemory(e.target.checked)}
                        />
                        {cronExtra.useMemory}
                      </label>
                    </div>
                  </div>
                )}
              </div>

            </div>

            <footer className="flex justify-end p-5 pt-3 border-t border-border shrink-0">
              <Button
                className="uppercase"
                size="sm"
                onClick={handleCreate}
                disabled={creating}
                prefix={creating ? <Spinner /> : undefined}
              >
                {creating ? t.common.creating : t.common.create}
              </Button>
            </footer>
          </div>
        </div>
      )}

      {/* Edit job modal */}
      {editJob && (
        <div
          ref={editModalRef}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4"
          onClick={(e) => e.target === e.currentTarget && setEditJob(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-cron-title"
        >
          <div className={cn(themedBody, "relative w-full max-w-lg max-h-[90vh] border border-border bg-card shadow-2xl flex flex-col")}>
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

            <div className="p-5 grid gap-4 overflow-y-auto flex-1 min-h-0">
              <div className="grid gap-2">
                <Label htmlFor="edit-cron-name">{t.cron.nameOptional}</Label>
                <Input
                  id="edit-cron-name"
                  autoFocus
                  placeholder={t.cron.namePlaceholder}
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="edit-cron-prompt">{t.cron.prompt}</Label>
                <textarea
                  id="edit-cron-prompt"
                  className="flex min-h-[80px] w-full border border-border bg-background/40 px-3 py-2 text-sm font-courier shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30 focus-visible:border-foreground/25"
                  placeholder={t.cron.promptPlaceholder}
                  value={editPrompt}
                  onChange={(e) => setEditPrompt(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="edit-cron-schedule">{t.cron.schedule}</Label>
                  <Input
                    id="edit-cron-schedule"
                    placeholder={t.cron.schedulePlaceholder}
                    value={editSchedule}
                    onChange={(e) => setEditSchedule(e.target.value)}
                  />
                </div>

                <div className="grid gap-2">
                  <Label htmlFor="edit-cron-deliver">{t.cron.deliverTo}</Label>
                  <Select
                    id="edit-cron-deliver"
                    value={editDeliver}
                    onValueChange={(v) => setEditDeliver(v)}
                  >
                    <SelectOption value="local">
                      {t.cron.delivery.local}
                    </SelectOption>
                    <SelectOption value="telegram">
                      {t.cron.delivery.telegram}
                    </SelectOption>
                    <SelectOption value="discord">
                      {t.cron.delivery.discord}
                    </SelectOption>
                    <SelectOption value="slack">
                      {t.cron.delivery.slack}
                    </SelectOption>
                    <SelectOption value="email">
                      {t.cron.delivery.email}
                    </SelectOption>
                  </Select>
                </div>
              </div>
              <div className="grid gap-2 border-t border-border pt-3">
                <Label>{cronExtra.contextToggles}</Label>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={editSilentNotice}
                    onChange={(e) => setEditSilentNotice(e.target.checked)}
                  />
                  {cronExtra.silentNotice}
                </label>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={editUseSoul}
                    onChange={(e) => setEditUseSoul(e.target.checked)}
                  />
                  {cronExtra.useSoul}
                </label>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={editUseUserMd}
                    onChange={(e) => setEditUseUserMd(e.target.checked)}
                  />
                  {cronExtra.useUserMd}
                </label>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={editUseMemory}
                    onChange={(e) => setEditUseMemory(e.target.checked)}
                  />
                  {cronExtra.useMemory}
                </label>
                <div className="grid gap-1.5">
                  <Label htmlFor="edit-cron-fallback">
                    {cronExtra.fallbackModels}
                  </Label>
                  <Input
                    id="edit-cron-fallback"
                    placeholder="deepseek:deepseek-chat, openai:gpt-4o-mini"
                    value={editFallback}
                    onChange={(e) => setEditFallback(e.target.value)}
                  />
                </div>
              </div>
            </div>

            <footer className="flex justify-end p-5 pt-3 border-t border-border shrink-0">
              <Button
                className="uppercase"
                size="sm"
                onClick={handleEdit}
                disabled={saving}
                prefix={saving ? <Spinner /> : undefined}
              >
                {saving ? t.common.loading : "Save changes"}
              </Button>
            </footer>
          </div>
        </div>
      )}

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
                    {profileLabel(profile.name)}
                  </SelectOption>
                ))}
              </Select>
            </div>
          </div>
        </div>

        {viewMode === "calendar" && (
          <CronCalendar profile={selectedProfile} />
        )}

        {viewMode === "list" && jobs.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              {t.cron.noJobs}
            </CardContent>
          </Card>
        )}

        {viewMode === "list" && jobs.map((job) => {
          const state = getJobState(job);
          const promptText = getJobPrompt(job);
          const title = getJobTitle(job);
          const hasName = Boolean(getJobName(job));
          const deliver = asText(job.deliver);
          const profile = getJobProfile(job);
          const jobKey = getJobKey(job);

          return (
            <Card key={jobKey}>
              <CardContent className="flex items-start gap-4 py-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-sm truncate">
                      {title}
                    </span>
                    <Badge tone={STATUS_TONE[state] ?? "secondary"}>
                      {state}
                    </Badge>
                    <Badge tone="outline">{profileLabel(profile)}</Badge>
                    {deliver && deliver !== "local" && (
                      <Badge tone="outline">{deliver}</Badge>
                    )}
                  </div>
                  {hasName && promptText && (
                    <p className="text-xs text-muted-foreground truncate mb-1">
                      {truncateText(promptText, 100)}
                    </p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="font-mono-ui">
                      {getJobScheduleDisplay(job, scheduleDescribeStrings)}
                    </span>
                    <span className="flex items-center gap-1">
                      {job.last_run_at && job.last_status === "ok" && (
                        <span
                          className="inline-block text-success"
                          title="Última ejecución exitosa"
                          aria-label="ok"
                        >
                          ✓
                        </span>
                      )}
                      {job.last_run_at && job.last_status === "error" && (
                        <span
                          className="inline-block text-destructive"
                          title="Última ejecución falló"
                          aria-label="error"
                        >
                          ✗
                        </span>
                      )}
                      {t.cron.last}: {formatTime(job.last_run_at)}
                    </span>
                    <span>
                      {t.cron.next}: {formatTime(job.next_run_at)}
                    </span>
                  </div>
                  {job.last_error && (
                    <p className="text-xs text-destructive mt-1">
                      {job.last_error}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <Button
                    ghost
                    size="icon"
                    title={state === "paused" ? t.cron.resume : t.cron.pause}
                    aria-label={
                      state === "paused" ? t.cron.resume : t.cron.pause
                    }
                    onClick={() => handlePauseResume(job)}
                    className={
                      state === "paused" ? "text-success" : "text-warning"
                    }
                  >
                    {state === "paused" ? <Play /> : <Pause />}
                  </Button>

                  <Button
                    ghost
                    size="icon"
                    title={t.cron.triggerNow}
                    aria-label={t.cron.triggerNow}
                    onClick={() => handleTrigger(job)}
                  >
                    <Zap />
                  </Button>

                  <Button
                    ghost
                    size="icon"
                    title="Edit job"
                    aria-label="Edit job"
                    onClick={() => openEditModal(job)}
                  >
                    <Pencil />
                  </Button>

                  <Button
                    ghost
                    destructive
                    size="icon"
                    title={t.common.delete}
                    aria-label={t.common.delete}
                    onClick={() => jobDelete.requestDelete(jobKey)}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <PluginSlot name="cron:bottom" />
    </div>
  );
}
