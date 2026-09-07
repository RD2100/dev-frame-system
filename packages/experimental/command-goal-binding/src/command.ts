/**
 * `/goal-complete` command grammar and rendering: input parsing, the stable
 * data-error texts, the completion-verdict renderings, and the receipt
 * evidence summary. Rendered text never exposes goal identities or revisions
 * (the `command-goal` precedent); verdict evidence stays stage-shaped.
 * @module @deepseek-ai/dsh-experimental-command-goal-binding/command
 */

import type {
  CompletionAdmissionAdmitted,
  CompletionAdmissionVerdict,
} from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
/** The slash-command name this plugin registers (without the leading slash). */
export const COMMAND_NAME = 'goal-complete'

/** Input hint advertised to capable command composers. */
export const COMMAND_HINT = '[<worktreePath>]'

/** Human-readable discovery summary for the command descriptor. */
export const GOAL_COMPLETE_DESCRIPTION
  = 'complete the current goal through the verified completion admission'

/** Stable data error: no goal is current. */
export const NO_CURRENT_GOAL_TEXT
  = 'No goal is currently set. Create one with /goal before using /goal-complete.'

/** Stable data error: the current goal carries no completion binding. */
export const NO_BINDING_TEXT
  = 'The current goal has no completion binding in this composition. Start it through the goal-binding flow before /goal-complete.'

/** Stable data error: no verification evidence is attributed to the goal. */
export const NO_VERIFICATION_TEXT
  = 'The current goal has no attributed verification evidence in this session log. Run verification before /goal-complete.'

/** Stable data error: no review record is attributed to the goal. */
export const NO_REVIEW_TEXT
  = 'This session log holds no review record. Obtain an authorized review before /goal-complete.'

/**
 * Stable data error: the newest attributed verification predates the
 * accepted checks change (AT1-10) — it belongs to a superseded binding
 * generation, so it cannot satisfy the current acceptance.
 */
export const VERIFICATION_SUPERSEDED_TEXT
  = 'The newest verification for this goal predates the accepted checks change and belongs to a superseded generation. Re-verify under the current approved checks before /goal-complete.'

/**
 * Stable data error: the newest review predates the accepted checks change
 * (AT1-10) — it approved a superseded acceptance, so it cannot gate the
 * current generation's completion.
 */
export const REVIEW_SUPERSEDED_TEXT
  = 'The newest review for this goal predates the accepted checks change and approved a superseded acceptance. Obtain a new authorized review before /goal-complete.'

/** Stable data error: the current goal already completed. */
export const GOAL_ALREADY_COMPLETE_TEXT
  = 'The current goal is already complete.'

/** Stable data error: the devframe projection latched a replay failure. */
export const PROJECTION_FAILURE_TEXT
  = 'The devframe projection recorded a replay failure in this session log, so completion evidence cannot be trusted. /goal-complete refuses to proceed.'

/** Stable data error: neither the command line nor the config names a worktree. */
export const WORKTREE_REQUIRED_TEXT
  = '/goal-complete needs a worktree path: pass "/goal-complete <worktreePath>" or configure workspaceRoot on the plugin.'

/**
 * Parse the raw text following `/goal-complete`. The whole trimmed remainder
 * is one worktree path (paths may contain spaces); an empty remainder selects
 * the configured fallback.
 * @param rawInput - verbatim command text following the command name.
 * @returns the explicit worktree path, or `undefined` for the bare form.
 */
export function parseGoalCompleteInput(rawInput: string): string | undefined {
  const input = rawInput.trim()
  return input.length === 0 ? undefined : input
}

/**
 * Render the human-readable adjudication for one admission rejection. The
 * required-checks arm lists every unsatisfied check: the list length is
 * bounded by construction — the approved checklist is host-curated and its
 * exact set is pinned by the digest rendered alongside.
 * @param verdict - the rejected verdict returned by the admission conjunction.
 * @returns the stable, stage-prefixed error text without goal identities.
 */
export function renderCompletionRejection(
  verdict: Exclude<CompletionAdmissionVerdict, CompletionAdmissionAdmitted>,
): string {
  switch (verdict.stage) {
    case 'task-warning':
      return `Completion rejected at task-warning: the session recorded a ${verdict.warning} memory failure (via ${verdict.tool}) graded fail because the task's acceptance required the memory operation. Recover the memory surface and obtain a human-authorized resume before completing.`
    case 'source-fingerprint':
      return 'Completion rejected at source-fingerprint: the worktree no longer matches the source fingerprint recorded when the work was accepted. Re-run verification on the current tree, then obtain a human-authorized resume before completing.'
    case 'required-checks':
      return `Completion rejected at required-checks: ${verdict.verdict.digest} does not fully cover the executed checks (${verdict.verdict.violations
        .map(violation => `${violation.checkId}: ${violation.reason}`)
        .join('; ')}).`
    case 'review':
      return `Completion rejected at review: the authorized review decided ${verdict.decision} with ${verdict.findings.length} finding(s). Address the findings and obtain a passing review before completing.`
    /* v8 ignore next 2 -- CompletionAdmissionVerdict is closed and every rejection stage is handled above */
    default:
      return assertNeverStage(verdict)
  }
}

/** Fail loudly if a locally closed verdict union gains an unhandled arm. */
/* v8 ignore start -- closed-union backstop is unreachable without violating the TypeScript contract */
function assertNeverStage(verdict: never): string {
  return `unhandled completion rejection stage: ${JSON.stringify(verdict)}`
}
/* v8 ignore stop */

/**
 * Render the success adjudication.
 * @returns the stable success text without goal identities or revisions.
 */
export function renderCompletionSuccess(): string {
  return 'Goal complete. Source fingerprint verified, required checks satisfied, and the authorized review passed; a completion-admission receipt was recorded.'
}

/**
 * Build the durable receipt evidence entry for one admitted completion. The
 * summary is bounded and carries the goal identity, the approved-checks
 * digest, and the dual-value fingerprint statement — it is a session-log
 * record, not rendered command text.
 * @param goalId - the goal identity the admission completed.
 * @param admitted - the admitted verdict carrying the verified fingerprint
 *   and approved-checks digest.
 * @returns one `completion-admission` evidence entry stamped now.
 */
export function completionAdmissionEvidence(
  goalId: string,
  admitted: CompletionAdmissionAdmitted,
): { readonly kind: 'completion-admission'; readonly summary: string; readonly at: number } {
  return {
    kind: 'completion-admission',
    summary: `Goal ${goalId} completion admitted: source fingerprint verified (recorded equals fresh), required checks ${admitted.requiredChecksDigest} satisfied, authorized review passed.`,
    at: Date.now(),
  }
}

/** The frozen descriptor part of the command definition handed to the registry. */
export interface GoalCompleteCommandShape {
  /** Command name without the leading slash. */
  readonly name: typeof COMMAND_NAME
  /** Human-readable discovery summary. */
  readonly description: typeof GOAL_COMPLETE_DESCRIPTION
  /** Free-form input hint; the command takes no images. */
  readonly input: { readonly hint: typeof COMMAND_HINT }
}

/**
 * Assemble the immutable descriptor part of the command definition.
 * @returns the name/description/input triple for `ctx.commands.register`.
 */
export function goalCompleteDescriptor(): GoalCompleteCommandShape {
  return {
    name: COMMAND_NAME,
    description: GOAL_COMPLETE_DESCRIPTION,
    input: { hint: COMMAND_HINT },
  }
}

/** The slash-command name of the start verb (without the leading slash). */
export const DEVFRAME_START_COMMAND_NAME = 'devframe-start'

/** Input hint advertised to capable command composers for the start verb. */
export const DEVFRAME_START_HINT = '[<objective>]'

/** Human-readable discovery summary for the start command descriptor. */
export const DEVFRAME_START_DESCRIPTION
  = 'start a new bound goal and produce real verification evidence'

/** The slash-command name of the resume verb (without the leading slash). */
export const DEVFRAME_RESUME_COMMAND_NAME = 'devframe-resume'

/** Human-readable discovery summary for the resume command descriptor. */
export const DEVFRAME_RESUME_DESCRIPTION
  = 'resume the current bound goal after a stop or restart'

/** Stable data error: the start line names no objective. */
export const START_OBJECTIVE_REQUIRED_TEXT
  = '/devframe-start needs an objective: pass "/devframe-start <objective>".'

/** Stable data error: the config names no worktree for the start lane. */
export const START_WORKTREE_REQUIRED_TEXT
  = '/devframe-start needs a worktree path: configure workspaceRoot on the plugin; the command line cannot name one alongside the objective.'

/** Stable data error: a goal is already current and not complete. */
export const START_GOAL_RUNNING_TEXT
  = 'A goal is already current and not complete. Resume or complete it before using /devframe-start.'

/** Stable data error: the resume line carries unexpected input. */
export const RESUME_INPUT_UNEXPECTED_TEXT
  = '/devframe-resume takes no input. Invoke it as "/devframe-resume" with nothing after the command name.'

/** Stable data error: no goal is current for the resume lane. */
export const RESUME_NO_CURRENT_GOAL_TEXT
  = 'No goal is currently set. Start one with /devframe-start before using /devframe-resume.'

/** Stable data error: neither the log projection nor the store holds a binding. */
export const RESUME_NO_BINDING_RECORD_TEXT
  = 'The current goal has no goal-binding record in this session log or binding store, so it cannot be resumed through /devframe-resume.'

/**
 * Parse the raw text following `/devframe-start`. The whole trimmed remainder
 * is one objective (objectives may contain spaces); an empty remainder is a
 * data error at the handler, not a hidden default.
 * @param rawInput - verbatim command text following the command name.
 * @returns the trimmed objective, empty when the line is bare.
 */
export function parseDevframeStartInput(rawInput: string): string {
  return rawInput.trim()
}

/**
 * Parse the raw text following `/devframe-resume`. The whole trimmed
 * remainder must be empty; any residue is a data error at the handler.
 * @param rawInput - verbatim command text following the command name.
 * @returns the trimmed residue, empty for the bare form.
 */
export function parseDevframeResumeInput(rawInput: string): string {
  return rawInput.trim()
}

/**
 * Render the start success adjudication. The text reports the real executed
 * check count and the honest verification status and stays stage-shaped; it
 * never exposes the goal id, snapshot id, verification id, fingerprint, or
 * confirmation id.
 * @param checkCount - number of required checks the host really executed.
 * @param status - aggregate verification status of those real executions.
 * @returns the stable success text without opaque ids.
 */
export function renderStartSuccess(checkCount: number, status: 'passed' | 'failed'): string {
  return `Bound goal started. The role policy, goal binding, and verification evidence were recorded in this session log; required checks executed for real: ${checkCount}, verification status: ${status}.`
}

/**
 * Render the resume success adjudication. The text stays stage-shaped and
 * never exposes the goal id, revision, or confirmation id.
 * @returns the stable success text without opaque ids.
 */
export function renderResumeSuccess(): string {
  return 'Bound goal resumed. The updated goal binding was recorded in this session log and goal continuation is armed.'
}

/**
 * Render the resume-with-adoption success adjudication (AT1-10): the
 * approved checks changed since the goal started, so the resume opened a new
 * binding generation under the recomputed acceptance, re-verified the real
 * approved checks for it, and the superseded generation's evidence and
 * review no longer count. The text stays stage-shaped without opaque ids.
 * @returns the stable adoption success text without opaque ids.
 */
export function renderResumeAdoptedSuccess(): string {
  return 'Bound goal resumed under the changed approved checks. A new binding generation was recorded, the current checks were re-verified for it, and the superseded generation\'s evidence no longer counts.'
}

/** The frozen descriptor part of the start command definition. */
export interface DevframeStartCommandShape {
  /** Command name without the leading slash. */
  readonly name: typeof DEVFRAME_START_COMMAND_NAME
  /** Human-readable discovery summary. */
  readonly description: typeof DEVFRAME_START_DESCRIPTION
  /** Free-form input hint; the command takes no images. */
  readonly input: { readonly hint: typeof DEVFRAME_START_HINT }
}

/**
 * Assemble the immutable descriptor part of the start command definition.
 * @returns the name/description/input triple for `ctx.commands.register`.
 */
export function devframeStartDescriptor(): DevframeStartCommandShape {
  return {
    name: DEVFRAME_START_COMMAND_NAME,
    description: DEVFRAME_START_DESCRIPTION,
    input: { hint: DEVFRAME_START_HINT },
  }
}

/**
 * The frozen descriptor part of the resume command definition. The resume
 * verb advertises no input: the command registry rejects an empty hint, so
 * "no hint" is the absent `input` descriptor rather than an empty string.
 */
export interface DevframeResumeCommandShape {
  /** Command name without the leading slash. */
  readonly name: typeof DEVFRAME_RESUME_COMMAND_NAME
  /** Human-readable discovery summary. */
  readonly description: typeof DEVFRAME_RESUME_DESCRIPTION
}

/**
 * Assemble the immutable descriptor part of the resume command definition.
 * @returns the name/description pair for `ctx.commands.register`.
 */
export function devframeResumeDescriptor(): DevframeResumeCommandShape {
  return {
    name: DEVFRAME_RESUME_COMMAND_NAME,
    description: DEVFRAME_RESUME_DESCRIPTION,
  }
}

/** The slash-command name of the stop verb (without the leading slash). */
export const DEVFRAME_STOP_COMMAND_NAME = 'devframe-stop'

/** Human-readable discovery summary for the stop command descriptor. */
export const DEVFRAME_STOP_DESCRIPTION
  = 'request a human-authorized stop of the current bound goal'

/** The slash-command name of the abandon verb (without the leading slash). */
export const DEVFRAME_ABANDON_COMMAND_NAME = 'devframe-abandon'

/** Human-readable discovery summary for the abandon command descriptor. */
export const DEVFRAME_ABANDON_DESCRIPTION
  = 'abandon the stopped or unfinished bound goal and clear its native Goal without claiming completion'

/** Stable data error: the stop line carries unexpected input. */
export const STOP_INPUT_UNEXPECTED_TEXT
  = '/devframe-stop takes no input. Invoke it as "/devframe-stop" with nothing after the command name.'

/** Stable data error: no goal is current for the stop lane. */
export const STOP_NO_CURRENT_GOAL_TEXT
  = 'No goal is currently set. Start one with /devframe-start before using /devframe-stop.'

/** Stable data error: neither the log projection nor the store holds a stoppable binding. */
export const STOP_NO_BINDING_RECORD_TEXT
  = 'The current goal has no goal-binding record in this session log or binding store, so it cannot be stopped through /devframe-stop.'

/** Stable data error: a stop request is already pending for the current goal. */
export const STOP_ALREADY_PENDING_TEXT
  = 'A stop request is already pending for the current goal; /devframe-stop refuses to issue a second request while the stop flow is unresolved.'

/** Stable data error: the abandon line carries unexpected input. */
export const ABANDON_INPUT_UNEXPECTED_TEXT
  = '/devframe-abandon takes no input. Invoke it as "/devframe-abandon" with nothing after the command name.'

/** Stable data error: no goal is current for the abandon lane. */
export const ABANDON_NO_CURRENT_GOAL_TEXT
  = 'No goal is currently set. Start one with /devframe-start before using /devframe-abandon.'

/** Stable data error: neither the log projection nor the store holds an abandonable binding. */
export const ABANDON_NO_BINDING_RECORD_TEXT
  = 'The current goal has no goal-binding record in this session log or binding store, so it cannot be abandoned through /devframe-abandon.'

/** Stable data error: the binding is neither admission-open nor stopped. */
export const ABANDON_UNRESOLVED_STATE_TEXT
  = 'The current goal binding is neither admission-open nor stopped; resolve the pending stop flow before /devframe-abandon.'

/** Stable data error: the resume target binding is mid-stop. */
export const RESUME_STOP_PENDING_TEXT
  = 'The current goal has a pending stop; the stop flow must land the stopped binding before /devframe-resume can run.'

/**
 * Parse the raw text following `/devframe-stop`. The whole trimmed remainder
 * must be empty; any residue is a data error at the handler.
 * @param rawInput - verbatim command text following the command name.
 * @returns the trimmed residue, empty for the bare form.
 */
export function parseDevframeStopInput(rawInput: string): string {
  return rawInput.trim()
}

/**
 * Parse the raw text following `/devframe-abandon`. The whole trimmed
 * remainder must be empty; any residue is a data error at the handler.
 * @param rawInput - verbatim command text following the command name.
 * @returns the trimmed residue, empty for the bare form.
 */
export function parseDevframeAbandonInput(rawInput: string): string {
  return rawInput.trim()
}

/**
 * Render the stop success adjudication. The text stays stage-shaped and
 * never exposes the goal id, revision, or confirmation id.
 * @returns the stable success text without opaque ids.
 */
export function renderStopSuccess(): string {
  return 'Bound goal stop requested. The stop-requested binding was recorded in this session log and goal continuation is disarmed; the stop flow owns quiescence confirmation.'
}

/**
 * Render the abandon success adjudication. The text stays stage-shaped and
 * never exposes the goal id, revision, or confirmation id.
 * @returns the stable success text without opaque ids.
 */
export function renderAbandonSuccess(): string {
  return 'Bound goal abandoned. The native Goal was cleared behind a durable tombstone, the binding history was retained, and no completion was claimed.'
}

/**
 * The frozen descriptor part of the stop command definition. Like the resume
 * verb, the stop verb advertises no input: "no hint" is the absent `input`
 * descriptor rather than an empty string.
 */
export interface DevframeStopCommandShape {
  /** Command name without the leading slash. */
  readonly name: typeof DEVFRAME_STOP_COMMAND_NAME
  /** Human-readable discovery summary. */
  readonly description: typeof DEVFRAME_STOP_DESCRIPTION
}

/**
 * Assemble the immutable descriptor part of the stop command definition.
 * @returns the name/description pair for `ctx.commands.register`.
 */
export function devframeStopDescriptor(): DevframeStopCommandShape {
  return {
    name: DEVFRAME_STOP_COMMAND_NAME,
    description: DEVFRAME_STOP_DESCRIPTION,
  }
}

/**
 * The frozen descriptor part of the abandon command definition. Like the
 * resume verb, the abandon verb advertises no input.
 */
export interface DevframeAbandonCommandShape {
  /** Command name without the leading slash. */
  readonly name: typeof DEVFRAME_ABANDON_COMMAND_NAME
  /** Human-readable discovery summary. */
  readonly description: typeof DEVFRAME_ABANDON_DESCRIPTION
}

/**
 * Assemble the immutable descriptor part of the abandon command definition.
 * @returns the name/description pair for `ctx.commands.register`.
 */
export function devframeAbandonDescriptor(): DevframeAbandonCommandShape {
  return {
    name: DEVFRAME_ABANDON_COMMAND_NAME,
    description: DEVFRAME_ABANDON_DESCRIPTION,
  }
}
