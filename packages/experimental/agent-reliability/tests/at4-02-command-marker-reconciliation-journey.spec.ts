/**
 * AT4-02 命令已写标记但结果未记录 — 真实故障注入旅程。草案 = anchor-matrix
 * AT4-02 行："命令已写标记但结果未记录：对账或标 ambiguous、不自动重放、
 * 标记不重复"（现状"部分"："构造级对账缝已锚；真实『子进程写标记+宿主
 * 死亡』注入路径未测。故障注入用例归 P06"）。
 *
 * 三旅程状态表（本波只落测试，src/ 零改动；GAP 旅程不设文件，状态汇总
 * 登记于此——选 AT4-02 文件承载是因为它是三旅程数值序的入口，套件自上
 * 而下先读总表再读各旅程）：
 *
 * | 旅程 | 调查结论 | 落点 |
 * | --- | --- | --- |
 * | AT4-02 | `reconcileUncertainCall` 的 probe/retry 执行缝存在 | 本文件：真实 node 子进程写标记 + 文件/存活观测注入 |
 * | AT4-03 | `StopProcess.handle` 缝存在；`spawnSubprocess` 提供生产树终止（POSIX 组信号 / Windows taskkill /T） | tests/at4-03-process-tree-stop-journey.spec.ts |
 * | AT4-06 | 截止关闭缝已收口：截止（含）起 assertAdmitted 以 DEADLINE_CLOSED 拒绝，恢复唯显式重开 | tests/at4-06-admission-deadline-closed.spec.ts；有界取消半边仍 GAP 待裁定 |
 *
 * 断言面：probe 从真实文件证实命令效果 → settled 且永不重放、标记不重复；
 * probe 证实缺席 → 恰好重试一次；writer 仍在飞 → unresolved（ambiguous）
 * 且永不重发。宿主死亡 = 命令完成后丢弃结果并销毁第一个服务上下文（进程
 * 内模型），重开 = 新 Context 重挂服务后对账。
 *
 * 注入机制：`node -e` 真实子进程执行命令体（写标记文件 + 追加执行日志行），
 * probe/retry 全部由测试注入——probe 只做真实文件观测与进程存活观测，
 * retry 拉起真实子进程并等它 owned exit。
 *
 * 与 service.spec 进程内缝级用例的边界：service.spec/at2c-06 用内存计数
 * 桩（零文件、零进程）锚服务契约分支；本旅程用真实进程与磁盘状态驱动同
 * 一缝，断言外部世界（标记内容、日志行数、子进程 exit 码）而非组件自报。
 *
 * @module tests/at4-02-command-marker-reconciliation-journey
 */

import { spawn, type ChildProcess } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentReliability from '../src/index.ts'
import type { ReconciliationProbe } from '../src/index.ts'

/** One real `node -e` command process with its owned exit signal. */
interface OwnedCommand {
  readonly pid: number
  readonly child: ChildProcess
  readonly exited: Promise<{ exitCode: number | null; signal: NodeJS.Signals | null }>
}

/** Owned resources registered at acquisition; afterEach disposes to quiescence. */
const ownedCommands: OwnedCommand[] = []
const tempRoots: string[] = []

afterEach(async () => {
  for (const command of ownedCommands.splice(0)) {
    try {
      command.child.kill('SIGKILL')
    } catch {
      // The command already exited; its owned exit signal is awaited below.
    }
    await command.exited.catch(() => {})
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

/** Create the journey's private per-test temp root (mkdtemp; no shared paths). */
async function tempRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'at4-02-'))
  tempRoots.push(root)
  return root
}

/** One booted context with the reliability service mounted. */
async function bootReliability(): Promise<{ service: AgentReliability; dispose: () => Promise<void> }> {
  const ctx = new Context()
  await ctx.plugin(AgentReliability)
  return { service: ctx.agentReliability, dispose: () => ctx.fiber.dispose() }
}

/**
 * Spawn one real command child: it writes the marker once and appends one
 * journal line, after an optional delay. The child is registered for cleanup
 * at acquisition time.
 */
function runCommand(script: string): OwnedCommand {
  const child = spawn(process.execPath, ['-e', script], { stdio: 'ignore' })
  const exited = new Promise<{ exitCode: number | null; signal: NodeJS.Signals | null }>((resolve, reject) => {
    child.once('error', reject)
    child.once('close', (exitCode, signal) => { resolve({ exitCode, signal }) })
  })
  const pid = child.pid
  if (pid === undefined) throw new Error('the command child failed to spawn')
  const command: OwnedCommand = { pid, child, exited }
  ownedCommands.push(command)
  return command
}

/** The command body: write the marker, then journal one execution line. */
function writerScript(markerPath: string, journalPath: string, token: string, delayMs = 0): string {
  return `
const fs = require('node:fs')
setTimeout(() => {
  fs.writeFileSync(${JSON.stringify(markerPath)}, ${JSON.stringify(token)})
  fs.appendFileSync(${JSON.stringify(journalPath)}, 'executed\\n')
}, ${delayMs})
`
}

/** Fresh read of the execution journal; a missing file is the honest zero. */
async function journalLines(journalPath: string): Promise<number> {
  try {
    return (await readFile(journalPath, 'utf8')).split('\n').filter(line => line.length > 0).length
  } catch {
    // A missing journal file means the command body never executed.
    return 0
  }
}

/** Existence check on a process this test spawned (held handle: reliable on both platforms). */
function processAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'EPERM'
  }
}

/**
 * The real reconciliation probe: read the marker from disk; only call the
 * effect absent when no writer could still produce it. `writerPid` is the
 * in-flight writer this journey knows about, if any.
 */
function markerProbe(markerPath: string, writerPid: number | undefined): () => Promise<ReconciliationProbe> {
  return async () => {
    try {
      await readFile(markerPath, 'utf8')
      return { status: 'confirmed' }
    } catch {
      // The marker is absent; absence is only provable when no writer remains.
    }
    if (writerPid !== undefined && processAlive(writerPid)) return { status: 'still_uncertain' }
    return { status: 'absent' }
  }
}

describe('AT4-02 command marker reconciliation journey', () => {
  it('settles a completed command from the real marker file and never re-executes it', async () => {
    const root = await tempRoot()
    const marker = join(root, 'command-marker.json')
    const journal = join(root, 'command-journal.log')
    const token = `written-by-${randomUUID()}`

    // The command runs to completion in a real child; the owning harness dies
    // before its result is recorded — the outcome is dropped with the context.
    const first = await bootReliability()
    try {
      const command = runCommand(writerScript(marker, journal, token))
      expect(await command.exited).toEqual({ exitCode: 0, signal: null })
      // Readiness: owned exit event plus the durable marker on disk.
      expect(await readFile(marker, 'utf8')).toBe(token)
    } finally {
      await first.dispose()
    }

    // Reopen the run: a fresh context re-derives truth from the world.
    const reopened = await bootReliability()
    try {
      let retries = 0
      const verdict = await reopened.service.reconcileUncertainCall<string>({
        operation: 'write-command-marker',
        probe: markerProbe(marker, undefined),
        retry: async () => {
          retries += 1
          const second = runCommand(writerScript(marker, journal, token))
          await second.exited
          return token
        },
      })
      expect(verdict).toEqual({ status: 'settled', via: 'probe' })
      // The command is not automatically repeated: the retry path never ran.
      expect(retries).toBe(0)
      // The marker is not duplicated: exactly one execution line, original token.
      expect(await journalLines(journal)).toBe(1)
      expect(await readFile(marker, 'utf8')).toBe(token)
    } finally {
      await reopened.dispose()
    }
  }, 10_000)

  it('retries an absent command exactly once through a real child writer', async () => {
    const root = await tempRoot()
    const marker = join(root, 'command-marker.json')
    const journal = join(root, 'command-journal.log')
    const token = `written-by-${randomUUID()}`

    const { service, dispose } = await bootReliability()
    try {
      expect(await journalLines(journal)).toBe(0)
      const verdict = await service.reconcileUncertainCall<string>({
        operation: 'write-command-marker',
        probe: markerProbe(marker, undefined),
        retry: async () => {
          const command = runCommand(writerScript(marker, journal, token))
          const outcome = await command.exited
          if (outcome.exitCode !== 0) throw new Error(`the retried command failed: ${JSON.stringify(outcome)}`)
          return token
        },
      })
      expect(verdict).toEqual({ status: 'settled', via: 'retry', result: token })
      // The command body executed exactly once; the marker holds that write.
      expect(await journalLines(journal)).toBe(1)
      expect(await readFile(marker, 'utf8')).toBe(token)
    } finally {
      await dispose()
    }
  }, 10_000)

  it('marks a command ambiguous while its real writer is still in flight and never resends it', async () => {
    const root = await tempRoot()
    const marker = join(root, 'command-marker.json')
    const journal = join(root, 'command-journal.log')
    const token = `written-by-${randomUUID()}`

    const { service, dispose } = await bootReliability()
    try {
      // The writer is genuinely still in flight: it only writes after a delay
      // the reopen does not wait for, so the effect cannot be called absent.
      const writer = runCommand(writerScript(marker, journal, token, 5000))
      expect(processAlive(writer.pid)).toBe(true)
      const verdict = await service.reconcileUncertainCall<string>({
        operation: 'write-command-marker',
        probe: markerProbe(marker, writer.pid),
        retry: async () => {
          throw new Error('the retry must never run for an ambiguous command')
        },
      })
      expect(verdict).toEqual({ status: 'unresolved' })
      // No command body ever executed beyond the still-running original.
      expect(await journalLines(journal)).toBe(0)
    } finally {
      await dispose()
    }
  }, 10_000)
})
