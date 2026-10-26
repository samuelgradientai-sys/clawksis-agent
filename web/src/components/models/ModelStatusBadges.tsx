/** Small status atoms shared by the Models page catalog and the Model Settings panel. */
import { Cloud, HardDrive } from "lucide-react";
import { Spinner } from "@nous-research/ui/ui/components/spinner";

import type { ModelCatalogStrings } from "@/i18n/types";
import { MAIN_ROLE, type Reachability } from "@/lib/model-catalog";
import { cn } from "@/lib/utils";

export function LocalityTag({
  isLocal,
  copy,
}: {
  isLocal: boolean;
  copy: ModelCatalogStrings;
}) {
  const Icon = isLocal ? HardDrive : Cloud;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 px-1.5 py-0.5 text-xs font-medium",
        isLocal ? "bg-success/10 text-success" : "bg-muted text-text-secondary",
      )}
    >
      <Icon className="h-2.5 w-2.5" />
      {isLocal ? copy.local : copy.cloud}
    </span>
  );
}

const DOT: Record<Exclude<Reachability, "checking" | "unknown">, string> = {
  running: "bg-success",
  unreachable: "bg-destructive",
  on_demand: "bg-muted-foreground/60",
};

export function ReachabilityPill({
  state,
  copy,
  title,
}: {
  state: Reachability;
  copy: ModelCatalogStrings;
  title?: string;
}) {
  if (state === "unknown") return null;
  const label = {
    running: copy.running,
    unreachable: copy.unreachable,
    checking: copy.checking,
    on_demand: copy.onDemand,
  }[state];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 text-xs",
        state === "unreachable" ? "text-destructive" : "text-text-secondary",
      )}
      title={title || undefined}
      data-reachability={state}
    >
      {state === "checking" ? (
        <Spinner className="text-[10px]" />
      ) : (
        <span className={cn("inline-block h-1.5 w-1.5 rounded-full", DOT[state])} />
      )}
      {label}
    </span>
  );
}

/** "Main" / "aux · vision" badges for the slots a model fills. */
export function RoleBadges({
  roles,
  copy,
  auxLabel,
}: {
  roles: string[];
  copy: ModelCatalogStrings;
  auxLabel(task: string): string;
}) {
  return (
    <>
      {roles.map((role) =>
        role === MAIN_ROLE ? (
          <span
            key={role}
            className="inline-flex shrink-0 items-center bg-primary/15 px-1.5 py-0.5 text-display text-xs font-medium tracking-wider text-primary"
          >
            {copy.main}
          </span>
        ) : (
          <span
            key={role}
            className="inline-flex shrink-0 items-center bg-purple-500/10 px-1.5 py-0.5 text-display text-xs font-medium tracking-wider text-purple-600 dark:text-purple-400"
          >
            aux · {auxLabel(role)}
          </span>
        ),
      )}
    </>
  );
}
