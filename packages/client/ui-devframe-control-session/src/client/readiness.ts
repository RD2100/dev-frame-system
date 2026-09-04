import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-runtime/client'
import type { DevFrameReadinessSnapshot } from '@deepseek-ai/dsh-devframe-control-session/types'

/** The readiness subset consumed by the Global Controller sidebar action. */
export type GlobalControllerReadinessState = DevFrameReadinessSnapshot

/** The generated Host Remote face used by this browser-side projection. */
export interface GlobalControllerReadinessRemote {
  readonly devframeControlSessions?: {
    readonly readiness: (
      afterRevision: number,
      signal?: AbortSignal,
    ) => Promise<{
      readonly ok: true
      readonly value: DevFrameReadinessSnapshot
    } | {
      readonly ok: false
    }>
  }
}

type ReadinessMethod = NonNullable<GlobalControllerReadinessRemote['devframeControlSessions']>['readiness']

const INITIAL_READINESS: GlobalControllerReadinessState = {
  status: 'blocked',
  generation: 0,
  revision: 0,
  code: 'BOOTSTRAP_NOT_STARTED',
}

function blockedReadiness(): GlobalControllerReadinessState {
  return {
    status: 'blocked',
    generation: 0,
    revision: 0,
    code: 'CONTROLLER_UNAVAILABLE',
  }
}

/**
 * Owns one cancellable readiness long-poll for the sidebar Global Controller.
 * A stale or late Remote response cannot publish after restart or disposal.
 */
export class GlobalControllerReadiness {
  readonly store: SnapshotStore<GlobalControllerReadinessState> = createSnapshotStore(INITIAL_READINESS)

  private generation = 0
  private abort: AbortController | undefined

  /**
   * Start one readiness generation against the Host Remote face.
   * @param remote - generated Host Remote carrier.
   */
  start(remote: GlobalControllerReadinessRemote): void {
    this.stop()
    const generation = ++this.generation
    const controller = new AbortController()
    this.abort = controller
    this.store.set({
      status: 'starting',
      generation: 0,
      revision: 0,
    })
    void this.poll(remote, controller.signal, generation)
  }

  /** Stop the current poll and fence all late responses. */
  stop(): void {
    this.generation += 1
    this.abort?.abort()
    this.abort = undefined
  }

  private async poll(
    remote: GlobalControllerReadinessRemote,
    signal: AbortSignal,
    generation: number,
  ): Promise<void> {
    let readiness: ReadinessMethod | undefined
    try {
      readiness = remote.devframeControlSessions?.readiness
    } catch {
      this.publishBlocked(generation, signal)
      return
    }
    if (readiness === undefined) {
      this.publishBlocked(generation, signal)
      return
    }

    let afterRevision = -1
    while (this.isCurrent(generation, signal)) {
      let response: Awaited<ReturnType<NonNullable<GlobalControllerReadinessRemote['devframeControlSessions']>['readiness']>>
      try {
        response = await readiness(afterRevision, signal)
      } catch {
        this.publishBlocked(generation, signal)
        return
      }
      if (!this.isCurrent(generation, signal)) return
      if (!response.ok) {
        this.publishBlocked(generation, signal)
        return
      }
      afterRevision = response.value.revision
      this.store.set(response.value)
    }
  }

  private publishBlocked(generation: number, signal: AbortSignal): void {
    if (this.isCurrent(generation, signal)) this.store.set(blockedReadiness())
  }

  private isCurrent(generation: number, signal: AbortSignal): boolean {
    return this.generation === generation && !signal.aborted
  }
}
