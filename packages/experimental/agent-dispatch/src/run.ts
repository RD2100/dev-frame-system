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
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import {
  FileRequiredChecksConfigStore,
  decodeRequiredChecksConfig,
} from '@deepseek-ai/dsh-experimental-devframe'
import type {
  DevFrameRequiredChecksConfig,
  RequiredChecksConfigStore,
  RequiredChecksDigest,
} from '@deepseek-ai/dsh-experimental-devframe'
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
  static inject = ['projectController']

  static Config: z<ProjectRunConfig> = z.object({
    checksLedgerPath: z.string(),
  })

  /** Validated config; `checksLedgerPath` may be absent (honest refusals then). */
  private readonly config: ProjectRunConfig

  /** The file-backed registration store, built on first use. */
  private store?: RequiredChecksConfigStore

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
    if (this.ctx.projectController.lifecycleState !== 'admission_open') {
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
}
