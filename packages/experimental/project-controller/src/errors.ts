/** The stable error type for project-controller failures. */

/** Stable, machine-routable failure classifications for the project controller. */
export type ProjectControllerErrorCode =
  /** A task move its current state does not permit. */
  | 'PROJECT_CONTROLLER_ILLEGAL_TRANSITION'
  /** The dispatch budget is exhausted; no further task may enter `developing` until one leaves it. */
  | 'PROJECT_CONTROLLER_CONCURRENCY_EXCEEDED'
  /** The task id does not exist on the board. */
  | 'PROJECT_CONTROLLER_TASK_UNKNOWN'
  /** The task id already exists on the board. */
  | 'PROJECT_CONTROLLER_TASK_EXISTS'
  /** The caller of a controller-gated action is not bound as `controller`. */
  | 'PROJECT_CONTROLLER_NOT_CONTROLLER'
  /** A `blocked` or `failed` move is missing its reason, next action, or wake condition. */
  | 'PROJECT_CONTROLLER_INVALID_DETAIL'
  /** A config value is outside its serviceable range. */
  | 'PROJECT_CONTROLLER_INVALID_CONFIG'
  /** A dispatch-path move ran while project admission was not open. */
  | 'PROJECT_CONTROLLER_ADMISSION_CLOSED'
  /** A merge marker is unknown, already consumed, or names another task. */
  | 'PROJECT_CONTROLLER_MARKER_INVALID'
  /** Quiescence was confirmed while tasks still carry in-flight work. */
  | 'PROJECT_CONTROLLER_QUIESCENCE_INCOMPLETE'
  /** The storage domain refused a write, or the record on disk failed its schema. */
  | 'PROJECT_CONTROLLER_PERSISTENCE'

/**
 * Structured failure from task dispatch, lifecycle moves, or the merge gate,
 * so host admission and diagnostics can route on the code alone.
 */
export class ProjectControllerError extends Error {
  /** Stable machine-routable failure classification. */
  readonly code: ProjectControllerErrorCode

  /**
   * @param message - Human-readable rejection reason.
   * @param code - Stable failure classification.
   * @param options - Original storage failure, when one exists.
   */
  constructor(message: string, code: ProjectControllerErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'ProjectControllerError'
    this.code = code
  }
}
