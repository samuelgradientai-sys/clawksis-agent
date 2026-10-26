import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router";
import { Check, Moon } from "lucide-react";
import { api, type CronDeliveryTarget, type CronJob } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { DASHBOARD_MODAL_BACKDROP, DASHBOARD_MODAL_PANEL } from "@/lib/dashboard-modal-shell";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { cn } from "@/lib/utils";
import { fill, type TodayCopy } from "./copy";
import { dailyCron, dailyTime, defaultDeliver } from "./today-model";

interface NightlyDigestProps {
  copy: TodayCopy;
  /** Profile the cron job belongs to (cron routes take it explicitly). */
  profile: string;
}

interface DeliverOption {
  id: string;
  label: string;
}

function deliverOptions(copy: TodayCopy, targets: CronDeliveryTarget[]): DeliverOption[] {
  const platforms = targets
    .filter((t) => t.id !== "local" && t.id !== "origin")
    .map((t) => ({ id: t.id, label: t.home_target_set ? t.name : `${t.name} (${copy.nightlyNoHome})` }));
  return [
    ...platforms,
    { id: "origin", label: copy.nightlyDeliverOrigin },
    { id: "local", label: copy.nightlyDeliverLocal },
  ];
}

function scheduleLabel(copy: TodayCopy, job: CronJob): string {
  const time = dailyTime(job.schedule?.expr);
  return time ? fill(copy.nightlyEveryDay, { time }) : job.schedule_display || job.schedule?.display || "";
}


/** "Recibir este resumen cada noche": shows the existing nightly job, or creates one after a confirm. */
export function NightlyDigest({ copy, profile }: NightlyDigestProps) {
  const [existing, setExisting] = useState<CronJob | null>(null);
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getCronJobs(profile)
      .then((jobs) => {
        if (alive) setExisting(jobs.find((j) => j.name === copy.nightlyJobName) ?? null);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [copy.nightlyJobName, profile, created]);

  if (existing) {
    return (
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-tertiary">
        <Moon className="h-3.5 w-3.5 text-[rgb(var(--clawk-liquid-violet))]" aria-hidden />
        {fill(copy.nightlyActive, { schedule: scheduleLabel(copy, existing) })}
        <Link to="/cron" className="inline-flex min-h-[44px] items-center text-midground underline-offset-2 hover:underline">
          {copy.nightlyOpenCron}
        </Link>
      </p>
    );
  }
  return (
    <>
      {created ? (
        <p className="flex items-center gap-2 text-xs text-emerald-300">
          <Check className="h-3.5 w-3.5" aria-hidden /> {created}
        </p>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="clawk-liquid-chip inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full px-4 text-sm text-text-secondary transition-colors hover:text-midground"
        >
          <Moon className="h-4 w-4 text-[rgb(var(--clawk-liquid-violet))]" aria-hidden />
          {copy.nightlyButton}
        </button>
      )}
      {open && <NightlyDialog copy={copy} profile={profile} onClose={() => setOpen(false)} onCreated={setCreated} />}
    </>
  );
}

interface NightlyDialogProps {
  copy: TodayCopy;
  onClose: () => void;
  onCreated: (message: string) => void;
  profile: string;
}

const FIELD =
  "h-[44px] w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 text-base text-text-primary outline-none focus:border-[rgb(var(--clawk-liquid-violet)/0.6)] sm:text-sm";

function NightlyDialog({ copy, onClose, onCreated, profile }: NightlyDialogProps) {
  const [time, setTime] = useState("22:00");
  const [targets, setTargets] = useState<CronDeliveryTarget[]>([]);
  const [deliver, setDeliver] = useState("origin");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useModalBehavior({ open: true, onClose });

  useEffect(() => {
    api
      .getCronDeliveryTargets(profile)
      .then((res) => {
        setTargets(res.targets);
        setDeliver(defaultDeliver(res.targets));
      })
      .catch(() => {});
  }, [profile]);

  const schedule = dailyCron(time);
  const create = useCallback(async () => {
    if (!schedule) return;
    setSaving(true);
    setError(null);
    try {
      await api.createCronJob(
        { name: copy.nightlyJobName, prompt: copy.nightlyPrompt, schedule, deliver },
        profile,
      );
      onCreated(fill(copy.nightlyCreated, { time }));
      onClose();
    } catch (err) {
      setError(fill(copy.nightlyError, { error: errorMessage(err) }));
    } finally {
      setSaving(false);
    }
  }, [copy, deliver, onClose, onCreated, profile, schedule, time]);

  return createPortal(
    <div
      className={DASHBOARD_MODAL_BACKDROP}
      role="dialog"
      aria-modal="true"
      aria-labelledby="nightly-digest-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div ref={ref} className={cn(DASHBOARD_MODAL_PANEL, "clawk-liquid-panel max-w-md rounded-3xl p-5")}>
        <h2 id="nightly-digest-title" className="flex items-center gap-2 text-base font-semibold text-text-primary">
          <Moon className="h-4 w-4 text-[rgb(var(--clawk-liquid-violet))]" aria-hidden /> {copy.nightlyTitle}
        </h2>
        <p className="mt-2 text-sm text-text-tertiary">{copy.nightlyDescription}</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-[8rem_1fr]">
          <label className="flex flex-col gap-1 text-xs text-text-tertiary">
            {copy.nightlyTime}
            <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className={FIELD} />
            <span className="text-[0.7rem] opacity-80">{copy.nightlyTimeHint}</span>
          </label>
          <label className="flex flex-col gap-1 text-xs text-text-tertiary">
            {copy.nightlyDeliver}
            <select value={deliver} onChange={(e) => setDeliver(e.target.value)} className={FIELD}>
              {deliverOptions(copy, targets).map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error && <p className="mt-3 break-words text-sm text-rose-300">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="clawk-liquid-chip min-h-[44px] rounded-full px-5 text-sm text-text-secondary transition-colors hover:text-text-primary"
          >
            {copy.nightlyCancel}
          </button>
          <button
            type="button"
            onClick={() => void create()}
            disabled={!schedule || saving}
            className="min-h-[44px] rounded-full bg-[rgb(var(--clawk-liquid-violet))] px-5 text-sm font-medium text-white shadow-[0_8px_24px_rgb(var(--clawk-liquid-violet)/0.35)] transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {copy.nightlyConfirm}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
