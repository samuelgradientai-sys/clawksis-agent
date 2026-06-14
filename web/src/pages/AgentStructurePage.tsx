/**
 * Agent Structure section — la jerarquía y las reglas de delegación.
 *
 * Documenta el modelo de agentes de Clawksis: un Jefe / Orquestador que habla
 * con el usuario y delega en subagentes especializados que se "contratan" solo
 * cuando la tarea lo amerita. Es una vista estática (el diseño/contrato del
 * sistema), pensada para vivir justo debajo de Visualization en el nav.
 */

import { Crown, Radar, Search, Cog, PenLine, GitBranch, ListChecks, Clock } from "lucide-react";
import type { ComponentType } from "react";

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

function BossCard() {
  return (
    <div className="w-full max-w-xs rounded-xl border border-[var(--color-primary)] bg-[var(--color-primary)]/10 px-5 py-4 text-center shadow-sm">
      <div className="flex items-center justify-center gap-2">
        <Crown className="h-4 w-4 text-[var(--color-primary)]" />
        <span className="font-semibold text-foreground">Jefe / Orquestador</span>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">Habla con el usuario</p>
    </div>
  );
}

function SpecialistCard({ s }: { s: Specialist }) {
  const Icon = s.icon;
  return (
    <div className="flex h-full flex-col rounded-xl border border-border bg-card/40 p-4 transition-colors hover:border-emerald-500/50">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-emerald-500" />
        <span className="font-semibold text-foreground">{s.name}</span>
      </div>
      <p className="mt-0.5 text-xs font-medium text-emerald-600/90">{s.tagline}</p>
      <p className="mt-2 text-sm text-muted-foreground">{s.description}</p>
    </div>
  );
}

export default function AgentStructurePage() {
  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
      <header>
        <h1 className="text-xl font-semibold">Estructura de agentes</h1>
        <p className="text-sm text-muted-foreground">
          Jerarquía y delegación: cómo el jefe reparte el trabajo entre subagentes
          especializados.
        </p>
      </header>

      {/* Organigrama */}
      <section className="rounded-xl border border-border bg-card/20 p-5">
        {/* Jefe */}
        <div className="flex justify-center">
          <BossCard />
        </div>
        {/* tronco */}
        <div className="flex justify-center">
          <div className="h-8 w-px bg-border" />
        </div>
        {/* bus horizontal (solo en pantallas anchas) + ramas */}
        <div className="relative">
          <div className="absolute left-[12.5%] right-[12.5%] top-0 hidden h-px bg-border lg:block" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {SPECIALISTS.map((s) => (
              <div key={s.name} className="flex flex-col items-center">
                <div className="hidden h-8 w-px bg-border lg:block" />
                <SpecialistCard s={s} />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Reglas */}
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
