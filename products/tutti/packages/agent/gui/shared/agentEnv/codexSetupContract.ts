/**
 * Frontend contract for the Codex setup progress stream surfaced on the agent
 * provider status snapshot as `activeAction` (片3 progress-flow contract). The
 * backend slice that populates this field has its own source of truth; the
 * generated `AgentProviderStatus` type does not (yet) declare it, so the panel
 * reads it defensively and degrades to detection-only state when it is absent.
 */

export type CodexSetupStepStatus =
  | "pending"
  | "running"
  | "ok"
  | "error"
  | "skipped";

export interface CodexSetupStep {
  id: string;
  label: string | null;
  status: CodexSetupStepStatus;
  detail: string | null;
}

export type CodexSetupPhase =
  | "detect"
  | "install"
  | "repair"
  | "verify"
  | "done"
  | "error";

export interface CodexSetupActiveActionError {
  code: string | null;
  message: string | null;
}

export interface CodexSetupActiveAction {
  phase: CodexSetupPhase;
  steps: CodexSetupStep[];
  registry: string | null;
  log: string[];
  error: CodexSetupActiveActionError | null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

const STEP_STATUSES: ReadonlySet<CodexSetupStepStatus> = new Set([
  "pending",
  "running",
  "ok",
  "error",
  "skipped"
]);

const PHASES: ReadonlySet<CodexSetupPhase> = new Set([
  "detect",
  "install",
  "repair",
  "verify",
  "done",
  "error"
]);

function normalizeStep(value: unknown, index: number): CodexSetupStep | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const status = asString(record.status);
  return {
    id: asString(record.id) ?? `step-${index}`,
    label: asString(record.label),
    status:
      status && STEP_STATUSES.has(status as CodexSetupStepStatus)
        ? (status as CodexSetupStepStatus)
        : "pending",
    detail: asString(record.detail)
  };
}

/**
 * Defensively reads the `activeAction` field off an AgentProviderStatus-like
 * object. Returns null when the field is missing or malformed, which the panel
 * treats as "no live setup action in progress".
 */
export function readCodexSetupActiveAction(
  status: unknown
): CodexSetupActiveAction | null {
  const statusRecord = asRecord(status);
  if (!statusRecord) {
    return null;
  }
  const raw = asRecord(statusRecord.activeAction);
  if (!raw) {
    return null;
  }
  const phase = asString(raw.phase);
  const steps = Array.isArray(raw.steps)
    ? raw.steps
        .map((step, index) => normalizeStep(step, index))
        .filter((step): step is CodexSetupStep => step !== null)
    : [];
  const log = Array.isArray(raw.log)
    ? raw.log.filter((entry): entry is string => typeof entry === "string")
    : [];
  const errorRecord = asRecord(raw.error);
  return {
    phase:
      phase && PHASES.has(phase as CodexSetupPhase)
        ? (phase as CodexSetupPhase)
        : "detect",
    steps,
    registry: asString(raw.registry),
    log,
    error: errorRecord
      ? {
          code: asString(errorRecord.code),
          message: asString(errorRecord.message)
        }
      : null
  };
}
