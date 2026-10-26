/**
 * The agent's questions to the user (server→client requests): approve a
 * dangerous command, answer a clarify, type a sudo password or a secret.
 * A bottom sheet on a phone, a centred liquid panel on wider screens; one
 * request at a time, oldest first.
 */

import { useState } from "react";
import { KeyRound, MessageCircleQuestion, ShieldAlert } from "lucide-react";
import type { ApprovalChoice, ChatServerRequest, ClarifyQuestionView } from "./hooks/serverRequests";

type Answer = (request: ChatServerRequest, result: Record<string, unknown>) => void;

const CHOICE_LABEL: Record<ApprovalChoice, string> = {
  once: "Permitir una vez",
  session: "Permitir en esta sesión",
  always: "Permitir siempre",
  deny: "Denegar",
};

const BUTTON =
  "min-h-11 rounded-2xl px-4 py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40";
const PRIMARY = BUTTON + " bg-[#6C4FD6] text-white hover:bg-[#5a40c2]";
const SECONDARY = BUTTON + " clawk-liquid-chip border border-white/10 text-foreground hover:border-[#8B6DFF]/60";
const DANGER = BUTTON + " border border-destructive/50 bg-destructive/15 text-destructive hover:bg-destructive/25";
// 16px on phones: a smaller input font makes iOS zoom the page on focus.
const INPUT =
  "w-full rounded-2xl border border-white/10 bg-background/60 px-3.5 py-2.5 text-base text-foreground outline-none focus:border-[#8B6DFF]/70 sm:text-sm";

function ApprovalCard({ request, onAnswer }: { request: Extract<ChatServerRequest, { kind: "approval" }>; onAnswer: Answer }) {
  const allow = request.choices.filter((c) => c !== "deny");
  return (
    <>
      <p className="text-sm text-muted-foreground">{request.description}</p>
      {request.command && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-2xl border border-white/10 bg-black/30 p-3 font-mono text-xs text-foreground">
          {request.command}
        </pre>
      )}
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end">
        <button type="button" className={DANGER} onClick={() => onAnswer(request, { choice: "deny" })}>
          {CHOICE_LABEL.deny}
        </button>
        {allow.map((choice, i) => (
          <button
            key={choice}
            type="button"
            autoFocus={i === 0}
            className={i === 0 ? PRIMARY : SECONDARY}
            onClick={() => onAnswer(request, { choice })}
          >
            {CHOICE_LABEL[choice]}
          </button>
        ))}
      </div>
    </>
  );
}

/** A multi-select answer travels as a JSON array string, like the TUI's. */
function encodeAnswer(q: ClarifyQuestionView, picked: string[], typed: string): string | null {
  const free = typed.trim();
  if (q.multiSelect) {
    const values = free ? [...picked, free] : picked;
    return values.length ? JSON.stringify(values) : null;
  }
  return free || picked[0] || null;
}

function ClarifyQuestionField({
  q,
  picked,
  typed,
  onPick,
  onType,
}: {
  q: ClarifyQuestionView;
  picked: string[];
  typed: string;
  onPick: (choice: string) => void;
  onType: (text: string) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium text-foreground">{q.question}</legend>
      {q.choices && (
        <div className="flex flex-wrap gap-2">
          {q.choices.map((choice) => (
            <button
              key={choice}
              type="button"
              aria-pressed={picked.includes(choice)}
              onClick={() => onPick(choice)}
              className={
                SECONDARY + (picked.includes(choice) ? " border-[#8B6DFF]/80 bg-[#6C4FD6]/25" : "")
              }
            >
              {choice}
            </button>
          ))}
        </div>
      )}
      <input
        className={INPUT}
        value={typed}
        placeholder={q.choices ? "Otra respuesta (opcional)" : "Tu respuesta"}
        onChange={(e) => onType(e.target.value)}
      />
    </fieldset>
  );
}

function ClarifyCard({ request, onAnswer }: { request: Extract<ChatServerRequest, { kind: "clarify" }>; onAnswer: Answer }) {
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const [typed, setTyped] = useState<Record<string, string>>(request.answers);
  const pick = (q: ClarifyQuestionView, choice: string) =>
    setPicked((prev) => {
      const current = prev[q.qid] ?? [];
      const next = q.multiSelect
        ? current.includes(choice) ? current.filter((c) => c !== choice) : [...current, choice]
        : [choice];
      return { ...prev, [q.qid]: next };
    });
  const answers = Object.fromEntries(
    request.questions.map((q) => [q.qid, encodeAnswer(q, picked[q.qid] ?? [], typed[q.qid] ?? "")]),
  );
  const complete = Object.values(answers).some((a) => a !== null);
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        onAnswer(request, { answers });
      }}
    >
      {request.questions.map((q) => (
        <ClarifyQuestionField
          key={q.qid}
          q={q}
          picked={picked[q.qid] ?? []}
          typed={typed[q.qid] ?? ""}
          onPick={(choice) => pick(q, choice)}
          onType={(text) => setTyped((prev) => ({ ...prev, [q.qid]: text }))}
        />
      ))}
      <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
        <button type="button" className={SECONDARY} onClick={() => onAnswer(request, {})}>
          Omitir
        </button>
        <button type="submit" className={PRIMARY} disabled={!complete}>
          Responder
        </button>
      </div>
    </form>
  );
}

function SecretCard({
  request,
  onAnswer,
}: {
  request: Extract<ChatServerRequest, { kind: "sudo" | "secret" }>;
  onAnswer: Answer;
}) {
  const [value, setValue] = useState("");
  const label = request.kind === "sudo" ? "Contraseña de sudo" : request.envVar || "Valor secreto";
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onAnswer(request, { value });
      }}
    >
      {request.kind === "sudo" && request.command && (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-2xl border border-white/10 bg-black/30 p-3 font-mono text-xs">
          {request.command}
        </pre>
      )}
      {request.kind === "secret" && request.prompt && <p className="text-sm text-muted-foreground">{request.prompt}</p>}
      <input
        className={INPUT}
        type="password"
        autoFocus
        autoComplete="off"
        aria-label={label}
        placeholder={label}
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
        <button type="button" className={SECONDARY} onClick={() => onAnswer(request, { value: "" })}>
          Omitir
        </button>
        <button type="submit" className={PRIMARY} disabled={!value}>
          Enviar
        </button>
      </div>
    </form>
  );
}

const TITLES: Record<ChatServerRequest["kind"], { title: string; icon: typeof ShieldAlert }> = {
  approval: { title: "Aprobación requerida", icon: ShieldAlert },
  clarify: { title: "El agente te pregunta", icon: MessageCircleQuestion },
  sudo: { title: "Se necesita sudo", icon: KeyRound },
  secret: { title: "Se necesita un secreto", icon: KeyRound },
};

function RequestBody({ request, onAnswer }: { request: ChatServerRequest; onAnswer: Answer }) {
  switch (request.kind) {
    case "approval":
      return <ApprovalCard request={request} onAnswer={onAnswer} />;
    case "clarify":
      return <ClarifyCard request={request} onAnswer={onAnswer} />;
    default:
      return <SecretCard request={request} onAnswer={onAnswer} />;
  }
}

export function ServerRequestDialog({
  requests,
  liveSessionId,
  onAnswer,
}: {
  requests: ChatServerRequest[];
  liveSessionId: string | null;
  onAnswer: Answer;
}) {
  const request = requests[0];
  if (!request) return null;
  const { title, icon: Icon } = TITLES[request.kind];
  const elsewhere = !!request.sessionId && !!liveSessionId && request.sessionId !== liveSessionId;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/45 backdrop-blur-[2px] sm:items-center sm:p-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="clawk-liquid-panel flex max-h-[88dvh] w-full max-w-lg flex-col gap-4 overflow-y-auto rounded-t-3xl p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:rounded-3xl"
      >
        <div className="flex items-center gap-2.5">
          <span className="clawk-liquid-chip flex size-9 shrink-0 items-center justify-center rounded-2xl border border-[#6C4FD6]/40">
            <Icon className="size-4 text-[#8B6DFF]" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-foreground">{title}</h2>
            {elsewhere && <p className="text-xs text-muted-foreground">En otra conversación de este panel</p>}
          </div>
          {requests.length > 1 && (
            <span className="clawk-liquid-chip rounded-full px-2.5 py-1 text-xs text-muted-foreground">
              1 de {requests.length}
            </span>
          )}
        </div>
        <RequestBody key={request.id} request={request} onAnswer={onAnswer} />
      </div>
    </div>
  );
}
