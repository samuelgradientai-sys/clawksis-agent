/**
 * "Available models" — everything the selected profile can run right now, grouped Local / Cloud
 * by provider, with the models in use pinned on top and local servers' reachability. The usage
 * cards below it on the Models page only know models that already ran in a session; this panel
 * is the backend catalog (`/api/model/options`) the pickers and the chat select from.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ChevronDown, ChevronRight, Cloud, HardDrive, Layers, RefreshCw, Search } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Input } from "@nous-research/ui/ui/components/input";
import { Spinner } from "@nous-research/ui/ui/components/spinner";

import type { ModelCatalogStrings } from "@/i18n/types";
import type { AuxiliaryTaskAssignment } from "@/lib/api";
import { auxTaskLabel } from "@/lib/aux-tasks";
import {
  catalogModelCount,
  filterModelCatalog,
  MAIN_ROLE,
  type CatalogModel,
  type CatalogProvider,
  type InUseEntry,
  type ModelCatalog,
} from "@/lib/model-catalog";
import { cn } from "@/lib/utils";

import { fillCopy as fill, useCatalogCopy } from "./catalog-copy";
import { LocalityTag, ReachabilityPill, RoleBadges } from "./ModelStatusBadges";
import { UseAsMenu } from "./UseAsMenu";

/** Cloud catalogs can list hundreds of models; local servers rarely more than a handful. */
const COLLAPSED_MODEL_COUNT = 6;

interface PanelProps {
  catalog: ModelCatalog;
  auxTasks: AuxiliaryTaskAssignment[];
  loading: boolean;
  error: string | null;
  onRedetect(): void;
  onAssigned(): void;
}

export function AvailableModelsPanel({
  catalog,
  auxTasks,
  loading,
  error,
  onRedetect,
  onAssigned,
}: PanelProps) {
  const copy = useCatalogCopy();
  const [query, setQuery] = useState("");
  const [showUnconfigured, setShowUnconfigured] = useState(false);
  const visible = useMemo(() => filterModelCatalog(catalog, query), [catalog, query]);
  const auxLabel = (task: string) => auxTaskLabel(auxTasks, task);
  const searching = query.trim().length > 0;
  const nothingMatches =
    searching && !visible.local.length && !visible.cloud.length && !visible.inUse.length;

  const blockProps = { auxTasks, auxLabel, copy, onAssigned, expandAll: searching };

  return (
    <Card className="min-w-0 max-w-full">
      <CardHeader className="min-w-0 pb-3">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <Layers className="h-4 w-4 shrink-0 text-muted-foreground" />
            <CardTitle className="text-sm">{copy.title}</CardTitle>
            <span className="text-xs text-text-secondary">
              {fill(copy.modelCount, { n: catalogModelCount(catalog) })}
            </span>
          </div>
          <div className="flex min-w-0 items-center gap-2">
            <div className="relative min-w-0">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={copy.searchPlaceholder}
                aria-label={copy.searchPlaceholder}
                className="h-7 w-56 max-w-full pl-7 text-xs"
              />
            </div>
            <Button
              size="sm"
              outlined
              onClick={onRedetect}
              disabled={loading}
              className="h-7 shrink-0 text-xs uppercase"
              prefix={loading ? <Spinner /> : <RefreshCw className="h-3 w-3" />}
            >
              {copy.redetect}
            </Button>
          </div>
        </div>
        <p className="mt-1 text-xs text-text-secondary">{copy.subtitle}</p>
      </CardHeader>

      <CardContent className="min-w-0 space-y-5 pt-3">
        {error && <p className="text-xs text-destructive">{error}</p>}

        <InUseStrip entries={visible.inUse} searching={searching} copy={copy} auxLabel={auxLabel} />

        {nothingMatches ? (
          <p className="text-xs italic text-text-tertiary">{copy.noMatch}</p>
        ) : (
          <>
            <CatalogSection
              icon={<HardDrive className="h-3.5 w-3.5" />}
              title={copy.local}
              providers={visible.local}
              empty={
                searching ? null : (
                  <div className="flex flex-col gap-1 text-xs text-text-tertiary">
                    <span>{copy.localEmpty}</span>
                    <Link to="/cookbook" className="underline underline-offset-2 hover:text-foreground">
                      {copy.installLocal}
                    </Link>
                  </div>
                )
              }
              {...blockProps}
            />
            <CatalogSection
              icon={<Cloud className="h-3.5 w-3.5" />}
              title={copy.cloud}
              providers={visible.cloud}
              empty={null}
              {...blockProps}
            />
          </>
        )}

        {visible.unconfigured.length > 0 && (
          <div className="border-t border-border/40 pt-3">
            <button
              type="button"
              onClick={() => setShowUnconfigured((v) => !v)}
              className="flex items-center gap-1 text-xs text-text-secondary hover:text-foreground"
              aria-expanded={showUnconfigured}
            >
              {showUnconfigured ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              {fill(copy.unconfigured, { n: visible.unconfigured.length })}
            </button>
            {showUnconfigured && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {visible.unconfigured.map((p) => (
                  <span
                    key={p.slug}
                    className="border border-border/50 px-1.5 py-0.5 text-xs text-text-secondary"
                    title={p.warning || p.slug}
                  >
                    {p.name}
                  </span>
                ))}
                <Link to="/env" className="ml-1 text-xs underline underline-offset-2 hover:text-foreground">
                  {copy.addKeys}
                </Link>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function InUseStrip({
  entries,
  searching,
  copy,
  auxLabel,
}: {
  entries: InUseEntry[];
  searching: boolean;
  copy: ModelCatalogStrings;
  auxLabel(task: string): string;
}) {
  if (searching && !entries.length) return null;
  return (
    <section aria-label={copy.inUse} className="space-y-2">
      <h3 className="text-display text-xs font-medium tracking-wider text-text-tertiary">
        {copy.inUse}
      </h3>
      {entries.length === 0 ? (
        <p className="text-xs text-text-tertiary">{copy.inUseEmpty}</p>
      ) : (
        <ul className="grid min-w-0 gap-2 md:grid-cols-2">
          {entries.map((entry) => (
            <li
              key={entry.key}
              data-in-use-model={entry.model}
              className={cn(
                "flex min-w-0 flex-col gap-1 border bg-muted/20 px-3 py-2",
                entry.roles.includes(MAIN_ROLE) ? "border-primary/40" : "border-border/50",
              )}
            >
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <RoleBadges roles={entry.roles} copy={copy} auxLabel={auxLabel} />
                <LocalityTag isLocal={entry.isLocal} copy={copy} />
                <ReachabilityPill state={entry.reachability} copy={copy} />
              </div>
              <div className="min-w-0 truncate font-mono text-xs" title={entry.model}>
                {entry.model}
              </div>
              <div className="min-w-0 truncate text-xs text-text-secondary">{entry.providerName}</div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface BlockCommon {
  auxTasks: AuxiliaryTaskAssignment[];
  auxLabel(task: string): string;
  copy: ModelCatalogStrings;
  onAssigned(): void;
  /** While filtering, show every match instead of the collapsed head. */
  expandAll: boolean;
}

function CatalogSection({
  icon,
  title,
  providers,
  empty,
  ...common
}: BlockCommon & {
  icon: ReactNode;
  title: string;
  providers: CatalogProvider[];
  empty: ReactNode;
}) {
  if (!providers.length && !empty) return null;
  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-display text-xs font-medium tracking-wider text-text-tertiary">
        {icon}
        {title}
        <span className="font-mono normal-case tracking-normal">· {providers.length}</span>
      </h3>
      {providers.length === 0 ? (
        empty
      ) : (
        <div className="grid min-w-0 gap-3 lg:grid-cols-2">
          {providers.map((provider) => (
            <ProviderBlock key={provider.slug} provider={provider} {...common} />
          ))}
        </div>
      )}
    </section>
  );
}

function ProviderBlock({
  provider,
  auxTasks,
  auxLabel,
  copy,
  onAssigned,
  expandAll,
}: BlockCommon & { provider: CatalogProvider }) {
  const [expanded, setExpanded] = useState(false);
  const showAll = expanded || expandAll || provider.models.length <= COLLAPSED_MODEL_COUNT;
  const shown = showAll ? provider.models : provider.models.slice(0, COLLAPSED_MODEL_COUNT);

  return (
    <div
      data-provider={provider.slug}
      className={cn(
        "min-w-0 border bg-card/50",
        provider.inUse ? "border-primary/30" : "border-border/40",
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 border-b border-border/30 px-3 py-2">
        <span className="min-w-0 truncate text-xs font-medium">{provider.name}</span>
        <span className="min-w-0 truncate font-mono text-xs text-text-tertiary">{provider.slug}</span>
        {provider.isCurrent && (
          <span className="text-display text-xs tracking-wider text-primary">{copy.currentProvider}</span>
        )}
        <span className="ml-auto flex items-center gap-2">
          <ReachabilityPill state={provider.reachability} copy={copy} title={provider.probeError} />
          <span className="text-xs text-text-tertiary">{provider.models.length}</span>
        </span>
        {provider.localUrl && (
          <span className="basis-full truncate font-mono text-xs text-text-tertiary" title={provider.localUrl}>
            {provider.localUrl}
          </span>
        )}
        {provider.warning && <span className="basis-full text-xs text-warning">{provider.warning}</span>}
      </div>
      <ul className="py-1">
        {shown.map((model) => (
          <ModelRow
            key={model.id}
            provider={provider}
            model={model}
            auxTasks={auxTasks}
            auxLabel={auxLabel}
            copy={copy}
            onAssigned={onAssigned}
          />
        ))}
      </ul>
      {provider.models.length > COLLAPSED_MODEL_COUNT && !expandAll && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="w-full border-t border-border/30 px-3 py-1.5 text-left text-xs text-text-secondary hover:text-foreground"
        >
          {expanded ? copy.showLess : fill(copy.showAll, { n: provider.models.length })}
        </button>
      )}
    </div>
  );
}

function ModelRow({
  provider,
  model,
  auxTasks,
  auxLabel,
  copy,
  onAssigned,
}: Omit<BlockCommon, "expandAll"> & { provider: CatalogProvider; model: CatalogModel }) {
  const firstAux = model.roles.find((role) => role !== MAIN_ROLE) ?? null;
  return (
    <li
      data-model={model.id}
      className={cn(
        "flex min-w-0 items-center gap-2 px-3 py-1 hover:bg-muted/20",
        model.served === false && "opacity-60",
      )}
    >
      <span className="min-w-0 flex-1 truncate font-mono text-xs" title={model.id}>
        {model.id}
      </span>
      <RoleBadges roles={model.roles} copy={copy} auxLabel={auxLabel} />
      {model.served === false && <span className="shrink-0 text-xs text-warning">{copy.notServed}</span>}
      {model.detected && <span className="shrink-0 text-xs text-success">{copy.detected}</span>}
      <UseAsMenu
        compact
        provider={provider.slug}
        model={model.id}
        baseUrl={provider.assignBaseUrl}
        isMain={model.roles.includes(MAIN_ROLE)}
        mainAuxTask={firstAux}
        auxTasks={auxTasks}
        onAssigned={onAssigned}
      />
    </li>
  );
}
