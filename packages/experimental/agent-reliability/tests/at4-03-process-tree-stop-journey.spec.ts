/**
 * AT4-03 真实长跑子进程+孙进程心跳树终止 — 真实故障注入旅程。草案 =
 * anchor-matrix AT4-03 行："真实长跑子进程+孙进程心跳：停止属主项目→进程
 * 树终止、输出停、回调落定、writer 后释放"（现状"部分"："契约顺序已锚；
 * 真实孙进程心跳树终止未测（需真实进程树故障注入）。归 P06"）。
 *
 * 断言面：service.stopProject 返回 stopped 且回调序列落定（closeAdmission →
 * record:stop_requested → record:quiescence_confirmed → flush →
 * releaseWriter），stop 同时逐字关闭服务的 dispatch admission
 * （AGENT_RELIABILITY_ADMISSION_CLOSED / "admission is closed"）；树死亡双证
 * ——子进程 owned exit 事件（终止而非干净退出）+ 孙进程平台存在性核查；
 * 心跳输出在树死后 ≥4 个周期停摆；releaseWriter 时刻树已死（顺序断言）。
 *
 * 注入机制：processes() 缝注入真实 SubprocessHandle（spawnSubprocess 生产
 * 实现）：node -e 子进程自孳 node -e 孙进程，孙进程每 40ms 心跳写文件；
 * stop 的 handle.terminate() 走生产树终止（POSIX 组信号 / Windows
 * taskkill /T），不依赖 POSIX 信号语义，终止断言在两平台成立，无平台 skip。
 *
 * 与 service.spec 进程内缝级用例的边界：那边 agents=[]、桩 handle 锚委托
 * 契约顺序；本旅程用真实进程树驱动同一缝，死亡、输出、释放顺序全部断言
 * 外部可观测状态（exit 事实、进程表、心跳文件），不信组件自报。
 *
 * 平台纪律：孙进程死亡核查按平台取真实进程表面——POSIX process.kill(pid,0)
 * 的 ESRCH，Windows tasklist 进程表查询（与生产 taskkill /T 同族）；就绪
 * 一律等文件/事件信号（启动文件、心跳行数、exit 事件），心跳停摆是否定
 * 断言，等 ≥4 个周期为界；子进程资源在获取后立即注册清理（afterEach 兜底
 * 到 owned exit + 树缺席），临时根 mkdtemp 且删除带 Windows 句柄有界重试。
 *
 * @module tests/at4-03-process-tree-stop-journey
 */

import { spawnSync } from 'node:child_process'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { Context } from '@deepseek-ai/cordis'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { SessionId } from '@deepseek-ai/dsh-session'
import type { SubprocessHandle } from '@deepseek-ai/dsh-subprocess'
import { spawnSubprocess } from '../../../subprocess/subprocess-local/src/spawn.ts'
import AgentReliability, { AgentReliabilityError } from '../src/index.ts'
import type { StopProjectOptions } from '../src/index.ts'

const HEARTBEAT_MS = 40
const IDENTITY = { controllerSessionId: ControllerSessionId('controller-at4-03'), goalId: GoalId('goal-at4-03') }
const ADMISSION_CLOSED = { code: 'AGENT_RELIABILITY_ADMISSION_CLOSED', message: 'admission is closed' }

/** The real tree handle, registered at acquisition for afterEach disposal. */
let ownedTree: SubprocessHandle | undefined
const tempRoots: string[] = []

afterEach(async () => {
  // Dispose to quiescence: terminate is idempotent once the stop took the
  // tree; the owned exit signal and whole-tree absence are awaited before the
  // temp root goes away.
  const handle = ownedTree
  ownedTree = undefined
  if (handle !== undefined) {
    handle.terminate()
    await handle.done.catch(() => {})
    await handle.waitForExit()
  }
  for (const root of tempRoots.splice(0)) await removeTempRoot(root)
})

/**
 * Remove one temp root. Windows releases file handles asynchronously, so the
 * removal retries within a bounded budget sized to that contention.
 */
async function removeTempRoot(root: string): Promise<void> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      await rm(root, { recursive: true, force: true })
      return
    } catch (error) {
      if (attempt >= 10) throw error
      await delay(50)
    }
  }
}

/** The grandchild body: heartbeat the output file every HEARTBEAT_MS until killed. */
function heartbeatScript(heartbeatPath: string): string {
  return `
const fs = require('node:fs')
setInterval(() => fs.appendFileSync(${JSON.stringify(heartbeatPath)}, String(Date.now()) + '\\n'), ${HEARTBEAT_MS})
`
}

/** The child body: spawn the grandchild, publish both pids, then idle until stopped. */
function treeScript(heartbeatPath: string, startupPath: string): string {
  return `
const fs = require('node:fs')
const { spawn } = require('node:child_process')
const gc = spawn(process.execPath, ['-e', ${JSON.stringify(heartbeatScript(heartbeatPath))}], { stdio: 'ignore' })
if (gc.pid === undefined) process.exit(3)
fs.writeFileSync(${JSON.stringify(startupPath)}, JSON.stringify({ childPid: process.pid, grandchildPid: gc.pid }))
setInterval(() => {}, 1000)
`
}

/**
 * Whether the OS process table still carries `pid`. Platform-honest: POSIX
 * answers a zero-signal kill (ESRCH = absent, EPERM = present); Windows asks
 * tasklist, the same process-table family the production taskkill /T uses.
 */
function processPresent(pid: number): boolean {
  if (process.platform !== 'win32') {
    try {
      process.kill(pid, 0)
      return true
    } catch (error) {
      return (error as NodeJS.ErrnoException).code === 'EPERM'
    }
  }
  const listing = spawnSync('tasklist', ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'], { encoding: 'utf8' })
  if (listing.error !== undefined) throw listing.error
  return (listing.stdout ?? '').split('\n').some(line => line.includes(`,"${pid}",`))
}

/** Poll for the externally observable death of one pid; fresh reads every turn. */
async function waitForAbsence(pid: number, label: string): Promise<void> {
  const bound = Date.now() + 2000
  while (processPresent(pid)) {
    if (Date.now() > bound) throw new Error(`${label} (pid ${pid}) is still present after the stop`)
    await delay(25)
  }
}

/** Wait for the child's startup publication (pids of the whole tree). */
async function waitForStartup(startupPath: string): Promise<{ childPid: number; grandchildPid: number }> {
  return await vi.waitFor(async () =>
    JSON.parse(await readFile(startupPath, 'utf8')) as { childPid: number; grandchildPid: number },
  { timeout: 5000 })
}

/** The dispatch pre-step must reject with exactly the stable admission failure. */
function expectAssertRejected(assert: () => void, failure: { code: string; message: string }): void {
  try {
    assert()
    expect.unreachable('the dispatch pre-step must reject')
  } catch (error: unknown) {
    expect(error).toMatchObject(failure)
    expect(error).toBeInstanceOf(AgentReliabilityError)
  }
}

describe('AT4-03 process tree stop journey', () => {
  it.each(['manual', 'deadline'] as const)('stops a real heartbeat tree via %s: writer released after exit', async (trigger) => {
    const root = await mkdtemp(join(tmpdir(), 'at4-03-'))
    tempRoots.push(root)
    const heartbeat = join(root, 'heartbeat.log')
    const startup = join(root, 'tree-startup.json')
    const handle = spawnSubprocess({
      argv: [process.execPath, '-e', treeScript(heartbeat, startup)],
      cwd: root,
      graceMs: 2000,
      stdio: { stdin: 'ignore', stdout: { maxBytes: 1000 }, stderr: { maxBytes: 1000 } },
    })
    ownedTree = handle
    // The owned child exit event, registered before the stop flow reads it:
    // stop's quiescence gate awaits this same promise, so the flag is set by
    // releaseWriter time. Rejection is spawn-level failure; the awaited done
    // below surfaces it.
    const order: string[] = []
    let childExitObserved = false
    let grandchildAbsentAtRelease = false
    void handle.done.then(() => { childExitObserved = true }, () => {})

    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      service.openAdmission(IDENTITY)
      const ownerSession = SessionId('at4-03-tree-owner')
      const agent = {
        id: ownerSession,
        cancel: vi.fn(),
        whenIdle: vi.fn(async () => {}),
      } as unknown as Agent

      // Readiness: the child published both pids and the grandchild has
      // actually been beating — the two-process tree is real before anything
      // stops it.
      const published = await waitForStartup(startup)
      expect(processPresent(published.childPid)).toBe(true)
      await vi.waitFor(async () => {
        expect((await readFile(heartbeat, 'utf8')).split('\n').filter(line => line.length > 0).length)
          .toBeGreaterThanOrEqual(2)
      }, { timeout: 5000 })
      expect(processPresent(published.grandchildPid)).toBe(true)

      const options: StopProjectOptions = {
        agents: [agent],
        registry: { get: () => agent },
        goals: {
          disarm: () => undefined,
          pause: () => { throw new Error('pause is not expected without active goals') },
        },
        jobs: {
          list: () => [],
          kill: () => { throw new Error('kill is not expected without jobs') },
          wait: async () => { throw new Error('wait is not expected without jobs') },
        },
        processes: () => [{ ownerSession: agent.id, label: 'at4-03-heartbeat-tree', handle }],
        graceMs: 5000,
        closeAdmission: () => {
          service.closeAdmission()
          order.push('closeAdmission')
        },
        record: (observation) => { order.push(`record:${observation.status}`) },
        flush: async () => { order.push('flush') },
        releaseWriter: () => {
          order.push('releaseWriter')
          // The release-time snapshot: the tree must already be gone.
          grandchildAbsentAtRelease = !processPresent(published.grandchildPid)
        },
      }
      if (trigger === 'deadline') {
        service.openAdmission(IDENTITY, { deadline: Date.now() + 10, stop: options })
        await vi.waitFor(() => { expect(service.deadlineStopResult).toBeDefined() })
      }
      const result = await (trigger === 'deadline' ? service.deadlineStopResult : service.stopProject(options))

      // Callbacks settle in the productized order...
      expect(result).toEqual({ status: 'stopped', remaining: [] })
      expect(order).toEqual([
        'closeAdmission',
        'record:stop_requested',
        'record:quiescence_confirmed',
        'flush',
        'releaseWriter',
      ])
      // ...and the stop closed the service's dispatch admission fail-loud.
      expectAssertRejected(() => { service.assertAdmitted(IDENTITY) }, ADMISSION_CLOSED)

      // The tree ended, double-evidenced: the child's exit event fired with
      // termination facts (POSIX carries the death on the signal, Windows on
      // a forced exit code — both mean terminated, not a clean exit)...
      const outcome = await handle.done
      expect(outcome.signal !== null || outcome.exitCode !== 0).toBe(true)
      // ...and the grandchild is independently absent from the process table.
      await waitForAbsence(published.grandchildPid, 'the grandchild')

      // Writer ownership was released only after the tree ended.
      expect(childExitObserved).toBe(true)
      expect(grandchildAbsentAtRelease).toBe(true)

      // Output stops: the heartbeat file is byte-stable across ≥4 cadence
      // periods (the bound for this negative assertion, not a readiness wait).
      const stoppedBeats = await readFile(heartbeat, 'utf8')
      expect(stoppedBeats.length).toBeGreaterThan(0)
      await delay(HEARTBEAT_MS * 4)
      expect(await readFile(heartbeat, 'utf8')).toBe(stoppedBeats)
    } finally {
      await ctx.fiber.dispose()
    }
  }, 10_000)
})
