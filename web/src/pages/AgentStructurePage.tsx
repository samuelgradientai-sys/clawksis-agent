/**
 * Agent Structure section — organigrama VIVO e INTERACTIVO.
 *
 * El árbol lee el mismo feed de eventos que Visualization (gateway WS + poll de
 * /api/visualization/agent-events) y muestra los subagentes que el Jefe/
 * Orquestador realmente contrató (eventos subagent.spawn_requested / start /
 * complete). Es interactivo: al hacer clic en el Jefe o en un subagente se abre
 * un panel de detalle con su objetivo, estado y un registro de actividad en
 * vivo (herramientas/pasos). Cuando no hay subagentes contratados muestra un
 * empty-state, y deja como referencia los tipos de especialista y las reglas.
 *
 * Vive justo debajo de Visualization en el nav.
 */

import { useMemo, useState } from "react";

import {
  Crown,
  Radar,
  Search,
  Cog,
  PenLine,
  GitBranch,
  ListChecks,
  Clock,
  Bot,
  Loader2,
  CheckCircle2,
  Activity,
  X,
} from "lucide-react";
import type { ComponentType } from "react";

import { useActiveEventChannel } from "@/lib/eventChannelStore";

import type { GatewayEvent } from "../visualization/gatewayFeed";
import { useGatewayFeed } from "../visualization/gatewayFeed";
import { useAgentEventsFeed } from "../visualization/agentEventsFeed";
import { useMergedFeed } from "../visualization/mergedFeed";

// ── Organigrama vivo: subagentes realmente contratados ──────────────────────

const BOSS_ID = "__jefe__";

type HiredAgent = {
  id: string;
  goal: string;
  depth: number;
  active: boolean;
};

type ActivityItem = {
  key: string;
  label: string;
  active: boolean;
};

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

/**
 * Reconstruye la lista de subagentes contratados a partir del stream de
 * eventos. Mismo origen que el Comms Graph de Visualization: los eventos
 * subagent.* traen subagent_id / parent_id / depth / goal.
 */
function buildHiredAgents(events: GatewayEvent[]): HiredAgent[] {
  const subs = new Map<string, HiredAgent>();
  for (const ev of events) {
    const p = ev.payload;
    if (ev.type === "subagent.spawn_requested" || ev.type === "subagent.start") {
      const id = str(p.subagent_id) || `sub-${ev.id}`;
      const depth = typeof p.depth === "number" ? (p.depth as number) : 1;
      const existing = subs.get(id);
      const goal = str(p.goal) || existing?.goal || "Tarea delegada";
      subs.set(id, { id, goal, depth, active: true });
    } else if (ev.type === "subagent.complete") {
      const id = str(p.subagent_id);
      const n = id ? subs.get(id) : undefined;
      if (n) n.active = false;
    } else if (ev.type === "subagent.tool" || ev.type === "subagent.thinking") {
      const id = str(p.subagent_id);
      const n = id ? subs.get(id) : undefined;
      if (n) n.active = true;
    }
  }
  // Activos primero, luego por orden de aparición.
  return [...subs.values()].sort((a, b) => Number(b.active) - Number(a.active));
}

/** Línea de tiempo de actividad de un subagente concreto (sus pasos). */
function agentActivity(events: GatewayEvent[], id: string): ActivityItem[] {
  const out: ActivityItem[] = [];
  events.forEach((ev, idx) => {
    if (str(ev.payload.subagent_id) !== id) return;
    let label = "";
    let active = false;
    if (ev.type === "subagent.spawn_requested" || ev.type === "subagent.start") {
      label = `Contratado · ${str(ev.payload.goal) || "tarea delegada"}`;
    } else if (ev.type === "subagent.tool") {
      label = `Herramienta: ${str(ev.payload.tool_name) || "—"}`;
      active = true;
    } else if (ev.type === "subagent.thinking") {
      label = "Pensando…";
      active = true;
    } else if (ev.type === "subagent.complete") {
      label = "Terminó y reportó al jefe";
    } else {
      return;
    }
    out.push({ key: `${ev.id}-${idx}`, label, active });
  });
  return out.slice(-25);
}

function AgentDetailPanel({
  selected,
  hired,
  events,
  onClose,
}: {
  selected: string;
  hired: HiredAgent[];
  events: GatewayEvent[];
  onClose: () => void;
}) {
  const isBoss = selected === BOSS_ID;
  const agent = hired.find((a) => a.id === selected);
  const activity = useMemo(
    () => (isBoss ? [] : agentActivity(events, selected)),
    [events, selected, isBoss],
  );

  if (!isBoss && !agent) return null;

  const activeCount = hired.filter((a) => a.active).length;

  return (
    <div className="rounded-xl border border-[var(--color-primary)]/40 bg-card/60 p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          {isBoss ? (
            <Crown className="h-4 w-4 text-[var(--color-primary)]" />
          ) : (
            <Bot className="h-4 w-4 text-emerald-500" />
          )}
          <div>
            <h3 className="font-semibold text-foreground">
              {isBoss ? "Jefe / Orquestador" : agent!.goal}
            </h3>
            <p className="text-xs text-muted-foreground">
              {isBoss
                ? "Habla con el usuario, decide y delega"
                : `Subagente · ${agent!.active ? "trabajando" : "terminado"}${
                    agent!.depth > 1 ? ` · nivel ${agent!.depth}` : ""
                  }`}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Cerrar detalle"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {isBoss ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Stat label="Subagentes contratados" value={String(hired.length)} />
          <Stat label="Trabajando ahora" value={String(activeCount)} />
          <Stat label="Terminados" value={String(hired.length - activeCount)} />
        </div>
      ) : (
        <div>
          <div className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Activity className="h-3.5 w-3.5" /> Actividad en vivo
          </div>
          {activity.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Sin pasos registrados todavía para este subagente.
            </p>
          ) : (
            <ol className="space-y-1.5">
              {activity.map((item) => (
                <li key={item.key} className="flex items-center gap-2 text-sm">
                  <span
                    className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                      item.active ? "bg-emerald-500" : "bg-muted-foreground/40"
                    }`}
                  />
                  <span className="text-muted-foreground">{item.label}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-card/40 p-3 text-center">
      <div className="text-2xl font-semibold text-foreground">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function BossCard({
  subagentCount,
  selected,
  onSelect,
}: {
  subagentCount: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full max-w-xs rounded-xl border bg-[var(--color-primary)]/10 px-5 py-4 text-center shadow-sm transition-all hover:bg-[var(--color-primary)]/20 ${
        selected
          ? "border-[var(--color-primary)] ring-2 ring-[var(--color-primary)]/40"
          : "border-[var(--color-primary)]"
      }`}
    >
      <div className="flex items-center justify-center gap-2">
        <Crown className="h-4 w-4 text-[var(--color-primary)]" />
        <span className="font-semibold text-foreground">Jefe / Orquestador</span>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">Habla con el usuario</p>
      <p className="mt-2 text-xs text-muted-foreground">
        {subagentCount === 0
          ? "Sin subagentes contratados"
          : `${subagentCount} subagente${subagentCount === 1 ? "" : "s"} contratado${
              subagentCount === 1 ? "" : "s"
            }`}
      </p>
    </button>
  );
}

function HiredAgentCard({
  a,
  selected,
  onSelect,
}: {
  a: HiredAgent;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex h-full w-full flex-col rounded-xl border p-4 text-left transition-all hover:border-emerald-500/60 ${
        selected
          ? "border-emerald-500 ring-2 ring-emerald-500/30 bg-emerald-500/5"
          : a.active
            ? "border-emerald-500/60 bg-emerald-500/5"
            : "border-border bg-card/40"
      }`}
    >
      <div className="flex items-center gap-2">
        <Bot className="h-4 w-4 text-emerald-500" />
        <span className="truncate font-semibold text-foreground" title={a.goal}>
          {a.goal}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        {a.active ? (
          <span className="inline-flex items-center gap-1 text-emerald-500">
            <Loader2 className="h-3 w-3 animate-spin" /> Trabajando
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <CheckCircle2 className="h-3 w-3" /> Terminado
          </span>
        )}
        {a.depth > 1 && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            nivel {a.depth}
          </span>
        )}
      </div>
    </button>
  );
}

// ── Referencia estática: tipos de especialista + reglas ─────────────────────

type Specialist = {
  name: string;
  tagline: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
};

const SPECIALISTS: Specialist[] = [
  {
    name: "Monitoreo",
    tagline: "Crons y alertas",
    description:
      "Ejecuta crons y vigila condiciones (ej. estado de servicios). Calla mientras la condición no se cumpla; solo avisa cuando hay algo real que reportar.",
    icon: Radar,
  },
  {
    name: "Research",
    tagline: "Busca info",
    description: "Investiga o busca información cuando la tarea requiere indagar.",
    icon: Search,
  },
  {
    name: "Ejecución",
    tagline: "Tareas largas",
    description:
      "Resuelve tareas de varios pasos o de larga duración que el jefe no debe hacer en línea.",
    icon: Cog,
  },
  {
    name: "Redacción",
    tagline: "Tono natural",
    description:
      "Redacta el mensaje final con tono humano y natural, respetando el idioma del user.md.",
    icon: PenLine,
  },
];

type RuleBlock = {
  title: string;
  icon: ComponentType<{ className?: string }>;
  items: string[];
};

const RULES: RuleBlock[] = [
  {
    title: "Jerarquía",
    icon: GitBranch,
    items: [
      "El Jefe / Orquestador es el único que habla con el usuario: mantiene la conversación, gestiona los crons y decide qué hacer con cada tarea. Por defecto resuelve él mismo las tareas simples.",
      "Los subagentes especializados se contratan solo cuando una tarea lo amerita. Cada uno hace una sola cosa y reporta de vuelta al jefe, nunca al usuario directamente.",
    ],
  },
  {
    title: "Reglas de delegación",
    icon: ListChecks,
    items: [
      "El jefe evalúa cada tarea entrante. Si es simple → la hace él. Si es compleja, larga o de un dominio específico → contrata al subagente adecuado.",
      "El subagente recibe solo esa tarea, acotada y con instrucciones claras. No toma decisiones fuera de su encargo.",
      "Al terminar, el subagente devuelve el resultado al jefe y se cierra. No queda corriendo ni se reprograma a sí mismo.",
      "El jefe consolida lo que recibe y, si corresponde, es quien responde al usuario.",
    ],
  },
  {
    title: "Crons con agente asignado",
    icon: Clock,
    items: [
      "Cada cron puede especificar qué agente lo ejecuta (ej. agente: monitoreo para chequear servicios).",
      "Si no se especifica agente, lo toma el jefe y delega si hace falta.",
      "Se mantiene la lógica de condición: el agente asignado verifica en silencio en cada ejecución y solo notifica cuando la condición se cumple o cuando hay un problema concreto. Nada de alertas inservibles mientras se espera.",
    ],
  },
];

export default function AgentStructurePage() {
  const channel = useActiveEventChannel();
  const wsFeed = useGatewayFeed(channel);
  const pollFeed = useAgentEventsFeed();
  const feed = useMergedFeed(wsFeed, pollFeed);

  const hired = useMemo(() => buildHiredAgents(feed.events), [feed.events]);
  const [selected, setSelected] = useState<string | null>(null);

  // Si el seleccionado ya no existe (salvo el jefe), limpiar.
  const selectedExists =
    selected === BOSS_ID || (selected != null && hired.some((a) => a.id === selected));
  const activeSelection = selectedExists ? selected : null;

  const toggle = (id: string) => setSelected((cur) => (cur === id ? null : id));

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Estructura de agentes</h1>
          <p className="text-sm text-muted-foreground">
            Organigrama en vivo: hacé clic en el jefe o en un subagente para ver su detalle
            y actividad.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              feed.connected ? "bg-emerald-500" : "bg-muted-foreground/50"
            }`}
          />
          <span className="text-muted-foreground">
            {feed.connected ? "En vivo" : "Conectando…"}
          </span>
        </div>
      </header>

      {/* Organigrama vivo */}
      <section className="rounded-xl border border-border bg-card/20 p-5">
        <div className="flex justify-center">
          <BossCard
            subagentCount={hired.length}
            selected={activeSelection === BOSS_ID}
            onSelect={() => toggle(BOSS_ID)}
          />
        </div>

        {hired.length > 0 ? (
          <>
            <div className="flex justify-center">
              <div className="h-8 w-px bg-border" />
            </div>
            <div className="relative">
              <div className="absolute left-[12.5%] right-[12.5%] top-0 hidden h-px bg-border lg:block" />
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {hired.map((a) => (
                  <div key={a.id} className="flex flex-col items-center">
                    <div className="hidden h-8 w-px bg-border lg:block" />
                    <HiredAgentCard
                      a={a}
                      selected={activeSelection === a.id}
                      onSelect={() => toggle(a.id)}
                    />
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <p className="mt-6 text-center text-sm text-muted-foreground">
            Ningún subagente contratado en este momento. El jefe resuelve las tareas
            simples solo; cuando delegue una tarea a un especialista, aparecerá acá en
            vivo.
          </p>
        )}
      </section>

      {/* Panel de detalle del nodo seleccionado */}
      {activeSelection && (
        <AgentDetailPanel
          selected={activeSelection}
          hired={hired}
          events={feed.events}
          onClose={() => setSelected(null)}
        />
      )}

      {/* Referencia: tipos de especialista que el jefe puede contratar */}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Tipos de especialista que el jefe puede contratar
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {SPECIALISTS.map((s) => {
            const Icon = s.icon;
            return (
              <div
                key={s.name}
                className="flex h-full flex-col rounded-xl border border-border bg-card/40 p-4"
              >
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 text-emerald-500" />
                  <span className="font-semibold text-foreground">{s.name}</span>
                </div>
                <p className="mt-0.5 text-xs font-medium text-emerald-600/90">{s.tagline}</p>
                <p className="mt-2 text-sm text-muted-foreground">{s.description}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Reglas de delegación */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {RULES.map((block) => {
          const Icon = block.icon;
          return (
            <div key={block.title} className="rounded-xl border border-border bg-card/40 p-4">
              <div className="mb-3 flex items-center gap-2">
                <Icon className="h-4 w-4 text-[var(--color-primary)]" />
                <h2 className="font-semibold text-foreground">{block.title}</h2>
              </div>
              <ul className="space-y-2">
                {block.items.map((item, i) => (
                  <li key={i} className="flex gap-2 text-sm text-muted-foreground">
                    <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]/60" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </section>
    </div>
  );
}
