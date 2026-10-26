/** The "Mi Chrome" page's panels: status + switch, the 4 setup steps, the tabs the agent sees,
 *  and safety/limits with revoke. State and actions come from `useMyChrome`. */

import { useState, type ComponentType, type ReactNode } from "react";
import { CreditCard, Download, Globe, KeyRound, ListChecks, ShieldCheck } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { CopyButton } from "@nous-research/ui/ui/components/command-block";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Switch } from "@nous-research/ui/ui/components/switch";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { cn } from "@/lib/utils";
import type { MyChromeStatus, MyChromeTab } from "@/lib/api-my-chrome";
import { fill, myChromeCopy as copy } from "./copy";
import { hostOf, statusView, tabBadges } from "./my-chrome-model";
import type { MyChromeData } from "./useMyChrome";

interface PanelProps {
  children: ReactNode;
  icon: ComponentType<{ className?: string }>;
  title: string;
}

function Panel({ children, icon: Icon, title }: PanelProps) {
  return (
    <section aria-label={title} className="clawk-liquid-panel flex min-w-0 flex-col gap-4 rounded-3xl p-4 sm:p-5">
      <header className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-midground" aria-hidden />
        <h2 className="flex-1 text-sm font-semibold uppercase tracking-[0.12em] text-text-secondary">{title}</h2>
      </header>
      {children}
    </section>
  );
}

interface StatusHeroProps {
  data: MyChromeData;
  locale: string;
  status: MyChromeStatus;
}

export function StatusHero({ data, locale, status }: StatusHeroProps) {
  const view = statusView(status, copy, locale);
  return (
    <section className="clawk-liquid-panel flex min-w-0 flex-col gap-4 rounded-3xl p-4 sm:p-6">
      <div className="flex min-w-0 flex-col gap-2">
        <h2 className="text-lg font-semibold sm:text-xl">{copy.heroTitle}</h2>
        <p className="text-sm text-text-secondary">{copy.heroBody}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-1.5 rounded-full border border-border/60 px-2.5 py-1 text-xs">
          <span className={cn("size-2 rounded-full", view.dot)} aria-hidden />
          {view.label}
        </span>
        <span className="min-w-0 flex-1 text-xs text-text-tertiary">{view.detail}</span>
        <label className="flex items-center gap-2 text-sm">
          {data.busy === "toggle" && <Spinner />}
          {copy.enabledLabel}
          <Switch
            aria-label={copy.enabledLabel}
            checked={status.enabled}
            disabled={data.busy === "toggle"}
            onCheckedChange={data.setEnabled}
          />
        </label>
      </div>
      {!status.enabled && <p className="text-xs text-text-tertiary">{copy.enabledHint}</p>}
    </section>
  );
}

function Step({ children, index, title }: { children: ReactNode; index: number; title: string }) {
  return (
    <li className="flex min-w-0 gap-3">
      <span className="grid size-7 shrink-0 place-items-center rounded-full bg-[#6C4FD6]/20 text-xs font-semibold">
        {index}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <h3 className="text-sm font-medium">{title}</h3>
        {children}
      </div>
    </li>
  );
}

function PairingCode({ code }: { code: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-2xl border border-[#6C4FD6]/50 bg-[#6C4FD6]/10 p-3">
      <code className="block max-h-28 overflow-y-auto break-all font-mono text-[11px] leading-relaxed">{code}</code>
      <div className="flex flex-wrap items-center gap-2">
        <CopyButton text={code} label={copy.step3Copy} copiedLabel={copy.step3Copied} />
        <span className="text-xs text-text-tertiary">{copy.step3Once}</span>
      </div>
    </div>
  );
}

export function SetupSteps({ data, locale, status }: StatusHeroProps) {
  const pairedSince = status.paired_at ? new Date(status.paired_at * 1000).toLocaleString(locale) : "";
  return (
    <Panel icon={ListChecks} title={copy.setupTitle}>
      <ol className="flex flex-col gap-5">
        <Step index={1} title={copy.step1Title}>
          <p className="text-xs text-text-secondary">{copy.step1Body}</p>
          <Button
            className="w-full sm:w-auto"
            size="sm"
            onClick={data.download}
            disabled={data.busy === "download"}
            prefix={data.busy === "download" ? <Spinner /> : <Download className="h-4 w-4" />}
          >
            {copy.step1Action}
          </Button>
        </Step>
        <Step index={2} title={copy.step2Title}>
          <p className="text-xs text-text-secondary">{copy.step2Body}</p>
        </Step>
        <Step index={3} title={copy.step3Title}>
          <p className="text-xs text-text-secondary">
            {status.paired && !data.pairing ? fill(copy.step3Paired, { date: pairedSince }) : copy.step3Body}
          </p>
          {data.pairing && <PairingCode code={data.pairing} />}
          <Button
            className="w-full sm:w-auto"
            size="sm"
            outlined={Boolean(data.pairing)}
            onClick={data.pair}
            disabled={data.busy === "pair" || !status.enabled}
            prefix={data.busy === "pair" ? <Spinner /> : <KeyRound className="h-4 w-4" />}
          >
            {status.paired || data.pairing ? copy.step3Again : copy.step3Action}
          </Button>
        </Step>
        <Step index={4} title={copy.step4Title}>
          <p className="text-xs text-text-secondary">{copy.step4Body}</p>
        </Step>
      </ol>
    </Panel>
  );
}

function TabRow({ tab }: { tab: MyChromeTab }) {
  const badges = tabBadges(tab, copy);
  return (
    <li className="flex min-w-0 items-center gap-3 rounded-2xl bg-white/[0.03] px-3 py-2">
      <Globe className="h-4 w-4 shrink-0 text-text-tertiary" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">{tab.title || hostOf(tab.url)}</p>
        <p className="truncate font-mono text-[11px] text-text-tertiary">{hostOf(tab.url)}</p>
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-1">
        {badges.map((badge) => (
          <span key={badge} className="rounded-full border border-border/60 px-2 py-0.5 text-[10px] text-text-secondary">
            {badge}
          </span>
        ))}
      </div>
    </li>
  );
}

export function SharedTabs({ status }: { status: MyChromeStatus }) {
  const empty = status.connected ? copy.tabsNone : copy.tabsEmpty;
  return (
    <Panel icon={Globe} title={copy.tabsTitle}>
      {status.tabs.length === 0 ? (
        <p className="text-sm text-text-tertiary">{empty}</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {status.tabs.map((tab) => (
            <TabRow key={tab.id} tab={tab} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

/** How payments work: autonomous by default; the user's own switch makes the agent ask first. */
export function PaymentsPanel({ data, status }: { data: MyChromeData; status: MyChromeStatus }) {
  return (
    <Panel icon={CreditCard} title={copy.paymentsTitle}>
      <label className="flex items-start justify-between gap-3 rounded-2xl bg-white/[0.03] px-3 py-3 text-sm">
        <span className="flex min-w-0 flex-col gap-1">
          <span className="font-medium">{copy.confirmLabel}</span>
          <span className="text-xs text-text-secondary">
            {status.confirm_payments ? copy.paymentsConfirm : copy.paymentsAutonomous}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {data.busy === "payments" && <Spinner />}
          <Switch
            aria-label={copy.confirmLabel}
            checked={status.confirm_payments}
            disabled={data.busy === "payments"}
            onCheckedChange={data.setConfirmPayments}
          />
        </span>
      </label>
      <ul className="flex list-disc flex-col gap-2 pl-5 text-sm text-text-secondary">
        <li>{copy.paymentsInjection}</li>
        <li>{copy.paymentsAuth}</li>
        <li>{copy.paymentsOwner}</li>
      </ul>
    </Panel>
  );
}

export function SafetyPanel({ data, status }: { data: MyChromeData; status: MyChromeStatus }) {
  const [confirming, setConfirming] = useState(false);
  const revoke = () => void data.revoke().then(() => setConfirming(false), () => setConfirming(false));
  return (
    <Panel icon={ShieldCheck} title={copy.safetyTitle}>
      <ul className="flex list-disc flex-col gap-2 pl-5 text-sm text-text-secondary">
        <li>{copy.safetyStop}</li>
        <li>{copy.safetyTabs}</li>
        <li>{copy.safetyLimits}</li>
      </ul>
      {status.paired && (
        <Button className="w-full sm:w-auto" size="sm" destructive outlined onClick={() => setConfirming(true)}>
          {copy.revoke}
        </Button>
      )}
      <ConfirmDialog
        open={confirming}
        title={copy.revokeTitle}
        description={copy.revokeBody}
        confirmLabel={copy.revoke}
        cancelLabel="Cancelar"
        destructive
        loading={data.busy === "revoke"}
        onCancel={() => setConfirming(false)}
        onConfirm={revoke}
      />
    </Panel>
  );
}
