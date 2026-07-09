import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ComponentType,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Compass,
  FolderKanban,
  KeyRound,
  MessageSquare,
  MonitorCog,
  ShieldCheck,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

const STORAGE_KEY = "clawksis.onboarding.v2.completed";
const LEGACY_STORAGE_KEY = "clawksis.onboarding.v1.completed";

type TargetByText = {
  text: string;
  tags?: string[];
};

type OnboardingStep = {
  title: string;
  eyebrow: string;
  description: string;
  bullets: string[];
  icon: ComponentType<{ className?: string }>;
  path?: string;
  selector?: string;
  targetText?: TargetByText;
  placement?: "right" | "left" | "top" | "bottom" | "center";
};

type TargetRect = {
  top: number;
  left: number;
  width: number;
  height: number;
};

const STEPS: OnboardingStep[] = [
  {
    eyebrow: "Inicio",
    title: "Bienvenido a Clawksis",
    description:
      "Este recorrido te muestra cómo moverte por el dashboard y dónde están las funciones principales.",
    bullets: [
      "Usa Siguiente y Atrás para avanzar.",
      "Puedes saltarlo en cualquier momento.",
      "Puedes volver a abrirlo con ?onboarding=2.",
    ],
    icon: Sparkles,
    placement: "center",
  },
  {
    eyebrow: "Navegación",
    title: "La barra lateral es tu mapa",
    description:
      "Desde aquí saltas entre chat, modelos, skills, media, logs, configuración y el resto del sistema.",
    bullets: [
      "El tutorial resaltará elementos cuando pueda encontrarlos.",
      "Si estás en móvil, abre el menú lateral para ver más opciones.",
      "Cada sección tiene su propio propósito operativo.",
    ],
    icon: Compass,
    selector: "nav",
    placement: "right",
  },
  {
    eyebrow: "Chat",
    title: "Chat es el centro operativo",
    description:
      "Aquí conversas con Clawksis, retomas sesiones y ejecutas flujos de trabajo con el agente.",
    bullets: [
      "Crea conversaciones nuevas para separar tareas.",
      "Adjunta contexto cuando sea necesario.",
      "Evita pegar secretos o claves en el chat.",
    ],
    icon: MessageSquare,
    path: "/chat",
    selector: "textarea, [contenteditable='true'], main",
    placement: "top",
  },
  {
    eyebrow: "Proyectos",
    title: "Usa proyectos para aislar contexto",
    description:
      "Los proyectos agrupan conversaciones y permiten instrucciones propias para ese flujo de trabajo.",
    bullets: [
      "Crea un proyecto por negocio, cliente, repositorio o tarea grande.",
      "Agrega instrucciones claras y verificables.",
      "Los chats dentro del proyecto heredan esas instrucciones.",
    ],
    icon: FolderKanban,
    path: "/chat",
    targetText: {
      text: "proyecto",
      tags: ["button", "a", "div", "section", "aside"],
    },
    placement: "right",
  },
  {
    eyebrow: "Instrucciones",
    title: "Configurar abre las instrucciones del proyecto",
    description:
      "Este botón es el lugar clave: ahí editas nombre, descripción e instrucciones propias del proyecto.",
    bullets: [
      "Usa Configurar para escribir reglas del proyecto.",
      "Las instrucciones guían el chat dentro de esa carpeta.",
      "No deben pedir saltarse seguridad, permisos o confirmaciones.",
    ],
    icon: MonitorCog,
    path: "/chat",
    targetText: {
      text: "configurar",
      tags: ["button", "a", "[role='button']"],
    },
    placement: "left",
  },
  {
    eyebrow: "Modelos",
    title: "Modelos vive en la barra lateral",
    description:
      "Desde esta sección revisas y configuras modelos, proveedores y opciones de razonamiento.",
    bullets: [
      "Aquí decides qué modelo usar según costo, velocidad o calidad.",
      "Valida que el proveedor esté configurado antes de depender de él.",
      "Evita cambiar modelos a mitad de una operación crítica.",
    ],
    icon: Wrench,
    path: "/chat",
    targetText: {
      text: "modelos",
      tags: ["a", "button", "[role='button']"],
    },
    placement: "right",
  },
  {
    eyebrow: "Proveedor activo",
    title: "Selector de modelo/proveedor del chat",
    description:
      "En el chat también puedes ver o cambiar el modelo activo para la conversación.",
    bullets: [
      "El selector muestra el modelo actual, por ejemplo deepseek o el proveedor configurado.",
      "Úsalo con cuidado si la conversación ya tiene contexto importante.",
      "Para ajustes más completos entra a Modelos.",
    ],
    icon: Wrench,
    path: "/chat",
    targetText: {
      text: "deepseek",
      tags: ["button", "a", "[role='button']", "div"],
    },
    placement: "top",
  },
  {
    eyebrow: "Skills",
    title: "Skills para procedimientos repetibles",
    description:
      "Las skills convierten procedimientos frecuentes en capacidades reutilizables para el agente.",
    bullets: [
      "Activa solo las que entiendas.",
      "Revisa skills de terceros antes de usarlas.",
      "Mantén procedimientos sensibles con confirmación humana.",
    ],
    icon: Bot,
    path: "/skills",
    selector: "main",
    placement: "center",
  },
  {
    eyebrow: "Media",
    title: "Media está en la barra lateral",
    description:
      "Media concentra archivos, imágenes y resultados visuales generados o usados por el dashboard.",
    bullets: [
      "Revisa resultados antes de publicarlos.",
      "No expongas archivos sensibles.",
      "Limpia recursos temporales cuando ya no sean necesarios.",
    ],
    icon: MonitorCog,
    path: "/chat",
    targetText: {
      text: "media",
      tags: ["a", "button", "[role='button']"],
    },
    placement: "right",
  },
  {
    eyebrow: "Automatización",
    title: "Cron está en la barra lateral",
    description:
      "Cron sirve para tareas recurrentes o seguimientos automatizados cuando el flujo ya está claro.",
    bullets: [
      "Empieza con automatizaciones simples.",
      "No automatices acciones sensibles sin revisión.",
      "Monitorea logs y resultados.",
    ],
    icon: Clock,
    path: "/chat",
    targetText: {
      text: "cron",
      tags: ["a", "button", "[role='button']"],
    },
    placement: "right",
  },
  {
    eyebrow: "Seguridad",
    title: "Claves, permisos y operaciones sensibles",
    description:
      "La seguridad del proyecto depende de mínimos privilegios, revisión de cambios y no exponer secretos.",
    bullets: [
      "No pegues API keys en conversaciones.",
      "No abras servicios públicamente sin necesidad.",
      "Antes de push, revisa diff, build y secretos.",
    ],
    icon: KeyRound,
    path: "/keys",
    selector: "main",
    placement: "center",
  },
  {
    eyebrow: "Listo",
    title: "Ya puedes empezar",
    description:
      "La forma más segura de trabajar con Clawksis es por pasos pequeños: aislar, probar, revisar y recién después publicar.",
    bullets: [
      "Usa proyectos para separar contextos.",
      "Prueba cambios antes de reiniciar servicios.",
      "No hagas commit, push o merge sin revisar.",
    ],
    icon: ShieldCheck,
    placement: "center",
  },
];

function readCompleted(): boolean {
  if (typeof window === "undefined") return true;

  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return true;
  }
}

function clearCompleted(): void {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.removeItem(STORAGE_KEY);
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    /* localStorage puede estar bloqueado */
  }
}

function markCompleted(): void {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    /* localStorage puede estar bloqueado; cerramos solo en memoria */
  }
}

function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

function findByText({ text, tags }: TargetByText): HTMLElement | null {
  if (typeof document === "undefined") return null;

  const wanted = normalizeText(text);
  const tagSelector = tags?.length ? tags.join(",") : "button,a,[role='button'],div,section,aside,main";
  const candidates = Array.from(document.querySelectorAll<HTMLElement>(tagSelector));

  const matches = candidates
    .map((element) => {
      const content = normalizeText(element.innerText || element.textContent || "");

      if (!content.includes(wanted)) return null;

      const rect = element.getBoundingClientRect();

      if (rect.width <= 0 || rect.height <= 0) return null;

      const area = rect.width * rect.height;
      const exact = content === wanted ? 0 : 1;
      const starts = content.startsWith(wanted) ? 0 : 1;
      const buttonLike =
        element.tagName === "BUTTON" ||
        element.tagName === "A" ||
        element.getAttribute("role") === "button"
          ? 0
          : 1;

      return {
        element,
        score: exact * 100_000 + starts * 20_000 + buttonLike * 10_000 + area,
      };
    })
    .filter(Boolean) as Array<{ element: HTMLElement; score: number }>;

  matches.sort((a, b) => a.score - b.score);

  return matches[0]?.element ?? null;
}

function getStepTarget(step: OnboardingStep): HTMLElement | null {
  if (typeof document === "undefined") return null;

  if (step.selector) {
    const element = document.querySelector<HTMLElement>(step.selector);

    if (element) {
      element.scrollIntoView({ block: "center", inline: "center" });

      const rect = element.getBoundingClientRect();

      if (rect.width > 0 && rect.height > 0) return element;
    }
  }

  if (step.targetText) {
    const element = findByText(step.targetText);

    if (element) {
      element.scrollIntoView({ block: "center", inline: "center" });
    }

    return element;
  }

  return null;
}

function rectFromElement(element: HTMLElement | null): TargetRect | null {
  if (!element) return null;

  const rect = element.getBoundingClientRect();

  if (rect.width <= 0 || rect.height <= 0) return null;

  const padding = 10;

  return {
    top: Math.max(8, rect.top - padding),
    left: Math.max(8, rect.left - padding),
    width: Math.min(window.innerWidth - 16, rect.width + padding * 2),
    height: Math.min(window.innerHeight - 16, rect.height + padding * 2),
  };
}

function useSpotlightRect(open: boolean, step: OnboardingStep, stepIndex: number) {
  const [targetRect, setTargetRect] = useState<TargetRect | null>(null);

  const updateRect = useCallback(() => {
    if (!open || step.placement === "center") {
      setTargetRect(null);
      return;
    }

    setTargetRect(rectFromElement(getStepTarget(step)));
  }, [open, step]);

  useLayoutEffect(() => {
    updateRect();

    const id = window.setTimeout(updateRect, 350);

    return () => window.clearTimeout(id);
  }, [updateRect, stepIndex]);

  useEffect(() => {
    if (!open) return;

    window.addEventListener("resize", updateRect);
    window.addEventListener("scroll", updateRect, true);

    return () => {
      window.removeEventListener("resize", updateRect);
      window.removeEventListener("scroll", updateRect, true);
    };
  }, [open, updateRect]);

  return targetRect;
}

function cardPosition(rect: TargetRect | null, placement: OnboardingStep["placement"]) {
  const width = 420;
  const margin = 20;
  const estimatedHeight = 560;

  if (!rect || placement === "center") {
    return {
      left: "50%",
      top: "50%",
      transform: "translate(-50%, -50%)",
      width: `min(${width}px, calc(100vw - 32px))`,
    };
  }

  const rightSpace = window.innerWidth - (rect.left + rect.width);
  const leftSpace = rect.left;
  const belowSpace = window.innerHeight - (rect.top + rect.height);

  let left = rect.left + rect.width + margin;
  let top = rect.top;

  if (placement === "left" || (placement === "right" && rightSpace < width + margin && leftSpace > rightSpace)) {
    left = rect.left - width - margin;
  }

  if (placement === "top") {
    left = rect.left;
    top = rect.top - 280;
  }

  if (placement === "bottom" || top < margin) {
    left = rect.left;
    top = rect.top + rect.height + margin;
  }

  if (belowSpace < 220 && placement !== "top") {
    top = Math.max(margin, rect.top - 260);
  }

  left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
  top = Math.max(
    margin,
    Math.min(top, Math.max(margin, window.innerHeight - estimatedHeight - margin)),
  );

  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `min(${width}px, calc(100vw - 32px))`,
  };
}

export function FirstRunOnboarding() {
  const navigate = useNavigate();
  const location = useLocation();

  const [open, setOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);

  const step = STEPS[stepIndex];

  useEffect(() => {
    if (typeof window === "undefined") return;

    try {
      const params = new URLSearchParams(window.location.search);
      const forced = params.get("onboarding");

      if (forced === "1" || forced === "2") {
        clearCompleted();
        setOpen(true);
        setStepIndex(0);
        return;
      }
    } catch {
      /* ignore */
    }

    setOpen(!readCompleted());
  }, []);

  useEffect(() => {
    if (!open || !step.path) return;

    if (location.pathname !== step.path) {
      navigate(step.path, { replace: false });
    }
  }, [location.pathname, navigate, open, step.path]);

  const targetRect = useSpotlightRect(open, step, stepIndex);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        markCompleted();
        setOpen(false);
      }

      if (event.key === "ArrowRight") {
        setStepIndex((current) => Math.min(current + 1, STEPS.length - 1));
      }

      if (event.key === "ArrowLeft") {
        setStepIndex((current) => Math.max(current - 1, 0));
      }
    };

    window.addEventListener("keydown", onKeyDown);

    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const finish = useCallback(() => {
    markCompleted();
    setOpen(false);
  }, []);

  const progress = useMemo(
    () => ((stepIndex + 1) / STEPS.length) * 100,
    [stepIndex],
  );

  if (!open) return null;

  const Icon = step.icon;
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === STEPS.length - 1;
  const hasSpotlight = Boolean(targetRect);
  const position = cardPosition(targetRect, step.placement);

  return (
    <div
      className="fixed inset-0 z-[1000]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="clawksis-onboarding-title"
    >
      <div className="absolute inset-0 bg-black/70 backdrop-blur-[2px]" />

      {hasSpotlight && targetRect && (
        <>
          <div
            className="pointer-events-none absolute rounded-3xl border-2 border-white bg-white/10 shadow-[0_0_0_9999px_rgba(0,0,0,0.58),0_0_40px_rgba(255,255,255,0.25)] transition-all duration-300"
            style={{
              top: targetRect.top,
              left: targetRect.left,
              width: targetRect.width,
              height: targetRect.height,
            }}
          />

          <div
            className="pointer-events-none absolute rounded-3xl border border-white/40"
            style={{
              top: targetRect.top - 6,
              left: targetRect.left - 6,
              width: targetRect.width + 12,
              height: targetRect.height + 12,
            }}
          />
        </>
      )}

      <section
        className="absolute max-h-[calc(100vh-32px)] overflow-y-auto overscroll-contain rounded-3xl border border-white/15 bg-neutral-950/96 text-white shadow-2xl transition-all duration-300"
        style={position}
      >
        <div className="absolute inset-x-0 top-0 h-1 bg-white/10">
          <div
            className="h-full bg-white transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>

        <button
          type="button"
          className="absolute right-4 top-4 rounded-full border border-white/10 bg-white/5 p-2 text-white/70 transition hover:bg-white/10 hover:text-white"
          onClick={finish}
          aria-label="Cerrar tutorial"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="p-6">
          <div className="mb-5 flex items-start gap-4 pr-10">
            <div className="flex h-13 w-13 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/10">
              <Icon className="h-6 w-6" />
            </div>

            <div>
              <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-white/60">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {step.eyebrow}
              </div>

              <h2
                id="clawksis-onboarding-title"
                className="text-2xl font-semibold tracking-tight"
              >
                {step.title}
              </h2>
            </div>
          </div>

          <p className="mb-5 text-sm leading-6 text-white/74">
            {step.description}
          </p>

          <ul className="space-y-2.5">
            {step.bullets.map((bullet) => (
              <li key={bullet} className="flex gap-3 text-sm leading-6 text-white/78">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-white/80" />
                <span>{bullet}</span>
              </li>
            ))}
          </ul>

          <div className="sticky bottom-0 -mx-6 -mb-6 mt-6 flex items-center justify-between gap-3 border-t border-white/10 bg-neutral-950/95 px-6 py-4 backdrop-blur">
            <button
              type="button"
              className="rounded-xl px-3 py-2 text-sm font-medium text-white/60 transition hover:bg-white/5 hover:text-white"
              onClick={finish}
            >
              Saltar
            </button>

            <div className="flex items-center gap-2">
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-semibold text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
                onClick={() => setStepIndex((current) => Math.max(current - 1, 0))}
                disabled={isFirst}
              >
                <ChevronLeft className="h-4 w-4" />
                Atrás
              </button>

              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-sm font-semibold text-black transition hover:bg-white/90"
                onClick={() => {
                  if (isLast) {
                    finish();
                    return;
                  }

                  setStepIndex((current) => Math.min(current + 1, STEPS.length - 1));
                }}
              >
                {isLast ? "Finalizar" : "Siguiente"}
                {!isLast && <ChevronRight className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="mt-5 flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-white/35">
            <span>
              Paso {stepIndex + 1}/{STEPS.length}
            </span>
            <span>Esc para cerrar</span>
          </div>

          <div className="mt-3 grid grid-cols-11 gap-1.5">
            {STEPS.map((item, index) => (
              <button
                key={item.title}
                type="button"
                className={cn(
                  "h-1.5 rounded-full transition",
                  index === stepIndex
                    ? "bg-white"
                    : index < stepIndex
                      ? "bg-white/50"
                      : "bg-white/15 hover:bg-white/30",
                )}
                onClick={() => setStepIndex(index)}
                aria-label={`Ir al paso ${index + 1}: ${item.title}`}
              />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
