/**
 * The formal host bootstrap (`ctx.projectRun`): the orchestration host's
 * own initialization face for the formal task chain. The task lifecycle's
 * model-facing moves are owned downstream — `project_task` plans and starts
 * development, the delivery tools record real Worker deliveries and
 * independent lead reviews, and the integration path mints and consumes the
 * main-tree merge marker — so this service deliberately owns none of them.
 * What it owns is the host's authorization acts:
 *
 * 1. `startProject` opens board admission (the writer-ownership rule: a
 *    fresh process starts stopped and the host re-opens the project).
 * 2. `approveTaskChecks` registers one human-approved required-checks
 *    configuration under its canonical digest in the deployment's
 *    `FileRequiredChecksConfigStore`, returning the digest the delivery
 *    tools' `requiredChecksByTask` wiring carries for that task. The store
 *    file is the SAME ledger the delivery tools read; the deployment wires
 *    both to one path. Registration is idempotent — an identical
 *    configuration returns the existing digest.
 *
 * The service never approves a checklist by itself, never fabricates a
 * digest, and never touches the board's lifecycle moves.
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/run
 */

import z from '@deepseek-ai/schemastery'
import { Service, type Context } from '@deepseek-ai/cordis'
import { readFile } from 'node:fs/promises'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { WorktreeId as WorktreeIdBrand } from '@deepseek-ai/dsh-worktree-registry'
import {
  FileRequiredChecksConfigStore,
  RequiredChecksDigest,
  decodeRequiredChecksConfig,
} from '@deepseek-ai/dsh-experimental-devframe'
import type {
  DevFrameRequiredChecksConfig,
  RequiredChecksConfigStore,
} from '@deepseek-ai/dsh-experimental-devframe'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-workspace'
import type {} from '@deepseek-ai/dsh-worktree-registry'
// Loads the controller's Context augmentation so `ctx.projectController` types here.
import type {} from '@deepseek-ai/dsh-experimental-project-controller'

declare module '@deepseek-ai/cordis' {
  interface Context {
    projectRun: AgentProjectRun
  }
}

/** Stable machine-routable classifications of a bootstrap refusal. */
export type ProjectRunErrorCode =
  /** No checks ledger path is configured for the deployment. */
  | 'PROJECT_RUN_CHECKS_LEDGER_UNCONFIGURED'
  /** The board's admission is closed; the host must start the project first. */
  | 'PROJECT_RUN_ADMISSION_CLOSED'
  /** The task is not on the board; the formal chain must plan it first. */
  | 'PROJECT_RUN_TASK_UNKNOWN'
  /** No host scenario file is configured or it is unreadable. */
  | 'PROJECT_RUN_SCENARIO_UNAVAILABLE'
  /** The host scenario does not match the prepared ledger contents. */
  | 'PROJECT_RUN_SCENARIO_MISMATCH'

/** Structured refusal of a bootstrap act; never a fabricated approval. */
export class ProjectRunError extends Error {
  /** Stable machine-routable classification of this refusal. */
  readonly code: ProjectRunErrorCode

  /**
   * @param message - human-readable refusal reason naming the fix.
   * @param code - stable machine-routable error classification.
   * @param options - standard Error options carrying the underlying cause.
   */
  constructor(message: string, code: ProjectRunErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'ProjectRunError'
    this.code = code
  }
}

/** Plugin config (optional — the bootstrap refuses loud without the ledger). */
export interface ProjectRunConfig {
  /**
   * Path of the required-checks registration ledger the delivery tools read.
   * The deployment wires this and the delivery tools' `requiredChecksPath`
   * to the SAME file.
   */
  readonly checksLedgerPath?: string
  /**
   * Path of the host-owned candidate scenario file the `project_host_start`
   * tool consumes. Capabilities (anchor, worktrees, digests) come from this
   * file — never from model arguments. Unset, the tool is not registered.
   */
  readonly candidateScenarioPath?: string
}

/** One host-owned task entry of the candidate scenario file. */
export interface CandidateScenarioTask {
  /** The task id the entry serves. */
  readonly taskId: string
  /** The pre-built Worker worktree path, normalized. */
  readonly worktreePath: string
  /** The digest the prepared ledger holds for this task's checks. */
  readonly digest: string
  /** The approved checks the digest must resolve to. */
  readonly checks: DevFrameRequiredChecksConfig
}

/** The host-owned candidate scenario file's shape. */
export interface CandidateScenario {
  /** The repository the pre-built worktrees hang off. */
  readonly anchorPath: string
  /** The controller's own integration-target worktree, bound at bootstrap. */
  readonly targetWorktreePath?: string
  /** The lead's worktree, adopted but left free for the lead's dispatch. */
  readonly leadWorktreePath?: string
  readonly tasks: readonly CandidateScenarioTask[]
}

/** What one successful host start established. */
export interface CandidateHostReceipt {
  /** The adopted workspace id (stable across restarts — persisted rows). */
  readonly workspaceId: string
  /** The controller session that now holds the binding and the locks. */
  readonly controllerSessionId: string
  /** Per task: the worktree row id and the verified digest. */
  readonly tasks: { taskId: string; worktreeId: string; digest: string; coldLockHolder?: string }[]
  /** The lead tree's row id, for the controller's lead dispatch. */
  readonly leadWorktreeId?: string
  /** The board lifecycle state after the start. */
  readonly lifecycle: string
}

/** One approved task checkset: the task it serves and the approved checklist. */
export interface TaskChecksApproval {
  /** The task the approved checks serve. */
  readonly taskId: TaskId
  /** The human-approved required-checks configuration. */
  readonly checks: DevFrameRequiredChecksConfig
}

/**
 * The formal host bootstrap over the real board admission and the real
 * registration ledger. Mounted by the agent-dispatch plugin; the host calls
 * it before the chain runs.
 */
export class AgentProjectRun extends Service {
  static inject = ['projectController', 'agentBindings', 'workspaceRegistry', 'worktreeRegistry']

  static Config: z<ProjectRunConfig> = z.object({
    checksLedgerPath: z.string(),
    candidateScenarioPath: z.string(),
  })

  /** Validated config; `checksLedgerPath` may be absent (honest refusals then). */
  private readonly config: ProjectRunConfig

  /** The file-backed registration store, built on first use. */
  private store?: RequiredChecksConfigStore

  /** The scenario as last loaded by hostStart, for the bootstrap-phase consumers. */
  private cachedScenario?: CandidateScenario

  /** The target worktree path from the cached scenario, when hostStart ran. */
  get candidateTargetWorktreePath(): string | undefined {
    return this.cachedScenario?.targetWorktreePath
  }

  /** The task ids from the cached scenario, when hostStart ran. */
  get candidateTaskIds(): readonly string[] | undefined {
    return this.cachedScenario?.tasks.map(task => task.taskId)
  }

  /**
   * @param ctx - Mounting context.
   * @param config - Schema-validated config; `checksLedgerPath` is optional.
   */
  constructor(ctx: Context, config: ProjectRunConfig) {
    super(ctx, 'projectRun')
    this.config = config
  }

  /**
   * Open board admission — the host's writer-ownership act. A fresh process
   * starts `stopped`; only the host re-opens the project, and the controller
   * refuses every board move until it does.
   * @returns the lifecycle state after the start.
   */
  startProject() {
    return this.ctx.projectController.startProject()
  }

  /**
   * The one required-checks store this service owns — the same file-backed
   * ledger the bootstrap's approvals write and every other consumer in the
   * process must read, so the ledger has a single writer and a single path.
   * @returns The lazily built file store over the configured absolute path.
   */
  sharedChecksStore(): RequiredChecksConfigStore {
    return this.requireStore()
  }

  /**
   * Register one human-approved required-checks configuration for one task
   * under its canonical digest in the deployment's registration ledger — the
   * digest the delivery tools' `requiredChecksByTask` wiring carries for the
   * task. Idempotent: an identical configuration returns the existing
   * digest without touching the ledger.
   * @param approval - The task and its approved checklist.
   * @returns the registered digest.
   */
  async approveTaskChecks(approval: TaskChecksApproval): Promise<RequiredChecksDigest> {
    const checks = decodeRequiredChecksConfig(approval.checks)
    return await this.requireStore().save(checks)
  }

  /**
   * Confirm the board is open for admission — a host-facing preflight the
   * bootstrap composition can run before dispatching. The controller's own
   * admission error is the honest verdict; this face only names it earlier.
   * @param taskId - The task the preflight serves.
   * @returns the task's board record, admitted.
   */
  requireAdmittedTask(taskId: TaskId) {
    const record = this.ctx.projectController.find(taskId)
    if (record === undefined) {
      throw new ProjectRunError(
        `task "${String(taskId)}" is not on the board`,
        'PROJECT_RUN_TASK_UNKNOWN',
      )
    }
    if (this.ctx.projectController.lifecycle !== 'admission_open') {
      throw new ProjectRunError(
        'board admission is closed; the host must start the project first',
        'PROJECT_RUN_ADMISSION_CLOSED',
      )
    }
    return record
  }

  /** The registration store, or the honest unconfigured refusal. */
  private requireStore(): RequiredChecksConfigStore {
    if (this.store === undefined) {
      if (this.config.checksLedgerPath === undefined) {
        throw new ProjectRunError(
          'no checksLedgerPath is configured; the host must configure the deployment before approving checks',
          'PROJECT_RUN_CHECKS_LEDGER_UNCONFIGURED',
        )
      }
      this.store = new FileRequiredChecksConfigStore({ path: this.config.checksLedgerPath })
    }
    return this.store
  }

  /**
   * The candidate host bootstrap: adopt the host-prepared worktrees, bind the
   * calling session as the project controller, take the worktrees' writer
   * locks, open board admission, and verify every task's approved digest
   * against the shared ledger. All capability inputs come from the host-owned
   * scenario file — the calling model supplies none. Re-entrant after a
   * restart: the persisted workspace and worktree rows keep their ids, and
   * the locks are re-acquired for the (possibly new) controller session.
   * @param controllerSessionId - The calling session, bound as controller.
   * @returns the established identity receipt.
   */
  async hostStart(controllerSessionId: SessionId): Promise<CandidateHostReceipt> {
    if (this.config.candidateScenarioPath === undefined) {
      throw new ProjectRunError(
        'no candidateScenarioPath is configured; the host bootstrap face is unavailable',
        'PROJECT_RUN_SCENARIO_UNAVAILABLE',
      )
    }
    const scenario = JSON.parse(await readFile(this.config.candidateScenarioPath, 'utf8')) as CandidateScenario
    this.cachedScenario = scenario
    if (scenario.tasks.length === 0) {
      throw new ProjectRunError(
        `candidate scenario '${this.config.candidateScenarioPath}' lists no tasks`,
        'PROJECT_RUN_SCENARIO_MISMATCH',
      )
    }

    // The workspace row for the anchor persists across restarts; adopt the
    // pre-built worktrees once and reuse the registered rows afterwards.
    const known = this.ctx.workspaceRegistry.list().find(row => row.path === scenario.anchorPath)
      ?? await this.ctx.workspaceRegistry.create(scenario.anchorPath)
    await this.ctx.worktreeRegistry.reconcile(known.id, { adoptUnregistered: true })
    // The controller binds exactly one tree: the integration target. The
    // lead and worker trees stay free — their own holders take them through
    // their own dispatch, and a foreign holder would block that dispatch.
    let controllerWorktree: { worktreeId: WorktreeIdBrand; worktreePath: string } | undefined
    let leadWorktreeId: string | undefined
    if (scenario.targetWorktreePath !== undefined) {
      const holder = WorktreeLockHolder(controllerSessionId)
      const targetRow = this.ctx.worktreeRegistry.list(known.id).find(entry => entry.path === scenario.targetWorktreePath)
      if (targetRow === undefined) {
        throw new ProjectRunError(
          `target worktree '${scenario.targetWorktreePath}' is not registered under the adopted workspace`,
          'PROJECT_RUN_SCENARIO_MISMATCH',
        )
      }
      await this.ctx.worktreeRegistry.bind(targetRow.id, holder)
      controllerWorktree = { worktreeId: targetRow.id, worktreePath: targetRow.path }
    }
    if (scenario.leadWorktreePath !== undefined) {
      const leadRow = this.ctx.worktreeRegistry.list(known.id).find(entry => entry.path === scenario.leadWorktreePath)
      if (leadRow === undefined) {
        throw new ProjectRunError(
          `lead worktree '${scenario.leadWorktreePath}' is not registered under the adopted workspace`,
          'PROJECT_RUN_SCENARIO_MISMATCH',
        )
      }
      leadWorktreeId = String(leadRow.id)
    }
    const tasks: CandidateHostReceipt['tasks'] = []
    for (const task of scenario.tasks) {
      // The digest must resolve to exactly the host-approved checks.
      const digest = RequiredChecksDigest(task.digest)
      const approved = await this.requireStore().load(digest)
      if (JSON.stringify(approved) !== JSON.stringify(decodeRequiredChecksConfig(task.checks))) {
        throw new ProjectRunError(
          `task '${task.taskId}' digest '${task.digest}' does not resolve to the scenario's approved checks`,
          'PROJECT_RUN_SCENARIO_MISMATCH',
        )
      }
      const row = this.ctx.worktreeRegistry.list(known.id).find(entry => entry.path === task.worktreePath)
      if (row === undefined) {
        throw new ProjectRunError(
          `task '${task.taskId}' worktree '${task.worktreePath}' is not registered under the adopted workspace`,
          'PROJECT_RUN_SCENARIO_MISMATCH',
        )
      }
      tasks.push({ taskId: task.taskId, worktreeId: String(row.id), digest: String(digest) })
    }
    await this.ctx.agentBindings.bind({
      agentId: controllerSessionId,
      role: 'controller',
      ...(controllerWorktree !== undefined ? { worktree: controllerWorktree } : {}),
    })
    const admission = this.startProject()
    return {
      workspaceId: String(known.id),
      controllerSessionId: String(controllerSessionId),
      tasks,
      ...(leadWorktreeId !== undefined ? { leadWorktreeId } : {}),
      lifecycle: String(admission),
    }
  }
}
