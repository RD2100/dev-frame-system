/**
 * S7 — project memory cold recovery: append → new process → equal read-back
 * (design §2 S7).
 *
 * Mechanism B, two processes over one shared isolated root. `--phase write`
 * creates a real agent (`ctx.agentLoop.create`, provider `mock`), resolves the
 * memory spec (`resolveMemorySpec`, Vault under the shared root, appends
 * enabled), builds the real session-log receipt store
 * (`createSessionLogReceiptStore`), appends one note in the project domain and
 * one in the user domain through `ProjectMemoryService`, flushes, exits 0.
 * `--phase read` resumes the session cold (`ctx.agents.resume`), rehydrates
 * the receipts (`rehydrateMemoryReceipts`), builds a fresh service over the
 * same Vault and spec, then verifies: `read` by noteId → `found` +
 * `verified: true` + field-by-field equality with the write-time request;
 * `search` hits exactly one note per domain; retrying the same append →
 * `already_exists`; exactly two real `.md` files inside the Vault.
 *
 * CLI: `node --import tsx/esm s7-memory-cold.mjs --tree <worktree> --out <dir> --phase write|read --root <sharedRoot>`
 * @module harness/s7-memory-cold
 */

import { existsSync, mkdirSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { SessionId } from '@deepseek-ai/dsh-session'
import {
  ProjectMemoryService,
  createSessionLogReceiptStore,
  rehydrateMemoryReceipts,
  resolveMemorySpec,
} from '@deepseek-ai/dsh-experimental-project-memory'
import { bootComposition, parseCliArgs } from './lib/launch.mjs'
import { registerMockAdapter } from './lib/mock-adapter.mjs'
import {
  assembleVerdict,
  check,
  exitCodeForVerdict,
  readJsonIfExists,
  recordHarnessError,
  writeJsonOut,
  writeTextOut,
  writeVerdict,
} from './lib/evidence.mjs'

const USAGE
  = 'usage: node --import tsx/esm s7-memory-cold.mjs --tree <worktree> --out <dir> --phase write|read --root <sharedRoot>'
const SESSION_ID = 'accept-s7-memory'

/** The two notes the write phase appends (the read phase compares verbatim). */
const PROJECT_NOTE = {
  scope: 'project',
  sourceRef: 'session:accept-s7:note:project',
  kind: 'fact',
  body: 'Acceptance note recorded in the project namespace for v14 composition validation.',
  assertionStatus: 'observed',
}
const USER_NOTE = {
  scope: 'user',
  sourceRef: 'session:accept-s7:note:user',
  kind: 'preference',
  body: 'Acceptance preference recorded in the user namespace for v14 composition validation.',
  assertionStatus: 'confirmed',
  humanConfirmation: 'human:accept-s7',
}

/**
 * Boot the memory-capable composition over the shared root (both phases use
 * the identical plugin sequence).
 * @param {string} root - shared isolated root.
 * @returns {Promise<import('@deepseek-ai/cordis').Context>} the composition.
 */
async function bootMemoryComposition(root) {
  const { ctx } = await bootComposition([
    [mountAgentLoopTestDependencies, {}],
    [SessionProjectionRegistry],
    [AgentLoop, { agents: [] }],
    [JsonlSessionPersistence, { root: join(root, 'session-logs') }],
  ], root)
  registerMockAdapter(ctx)
  return ctx
}

/**
 * Resolve the memory spec for the shared Vault (identical in both phases).
 * @param {string} vaultRoot - the Vault root under the shared root.
 * @returns {ReturnType<typeof resolveMemorySpec>} the resolved spec.
 */
function memorySpec(vaultRoot) {
  return resolveMemorySpec({
    vaultRoot,
    writeEnabled: true,
    userScopeEnabled: true,
    workspaceId: 'ws-accept',
  })
}

/**
 * Write phase: append the two notes through the real service and flush.
 * @param {string} root - shared isolated root.
 * @param {string} outDir - the `--out` evidence directory.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function runWrite(root, outDir) {
  const vaultRoot = join(root, 'vault')
  const worktree = join(root, 'worktree')
  mkdirSync(vaultRoot, { recursive: true })
  mkdirSync(worktree, { recursive: true })

  const ctx = await bootMemoryComposition(root)
  const agent = ctx.agentLoop.create(SessionId(SESSION_ID), { provider: 'mock', model: 'mock' }, { cwd: worktree })
  const spec = memorySpec(vaultRoot)
  const store = createSessionLogReceiptStore(agent.session)
  const service = new ProjectMemoryService(spec, store)

  const projectAppend = await service.append(PROJECT_NOTE)
  const userAppend = await service.append(USER_NOTE)
  const receiptEvents = agent.session.snapshotEvents().filter(event => event.type === 'memory/receipt')
  const facts = {
    sessionId: agent.session.header.id,
    eventCount: agent.session.snapshotEvents().length,
    appends: { project: projectAppend, user: userAppend },
    receiptEventCount: receiptEvents.length,
  }
  await ctx.sessions.flush(agent.session)
  await ctx.fiber.dispose()

  const verdict = assembleVerdict({
    scenario: 's7-memory-cold (write phase)',
    checks: [
      check({
        id: 's7-write-appends-created',
        expectation: 'both appends report created and the session log holds one memory/receipt per note',
        pass: projectAppend.status === 'created' && userAppend.status === 'created' && receiptEvents.length === 2,
        observed: facts,
        evidence: 's7/write.json',
      }),
    ],
    notes: [
      'resolveMemorySpec 追加 userScopeEnabled: true：user 域 note 的写入需要显式 user scope 允许（否则 MEMORY_SCOPE_FORBIDDEN）—— 已登记偏差（design 文本仅列 vaultRoot/writeEnabled/workspaceId）',
    ],
  })
  // The verdict rides inside write.json so the read phase can combine both.
  await writeJsonOut(outDir, 's7/write.json', {
    exitcode: 0,
    verdict: verdict.verdict,
    requests: { project: PROJECT_NOTE, user: USER_NOTE },
    facts,
  })
  await writeVerdict(outDir, verdict)
  return exitCodeForVerdict(verdict)
}

/**
 * Read phase: cold resume, rehydrate receipts, and verify equal read-back.
 * @param {string} root - shared isolated root.
 * @param {string} outDir - the `--out` evidence directory.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function runRead(root, outDir) {
  const write = await readJsonIfExists(join(outDir, 's7', 'write.json'))
  if (write === undefined) {
    const verdict = assembleVerdict({
      scenario: 's7-memory-cold',
      checks: [],
      blocked: { reason: '缺少 write 阶段产物 s7/write.json：先运行 --phase write，再运行 --phase read' },
    })
    await writeVerdict(outDir, verdict)
    return exitCodeForVerdict(verdict)
  }
  const vaultRoot = join(root, 'vault')
  const ctx = await bootMemoryComposition(root)
  const handle = await ctx.agents.resume({
    resumeSessionId: SessionId(SESSION_ID),
    agentOptions: { provider: 'mock', model: 'mock' },
  })
  const agent = handle.agent
  const spec = memorySpec(vaultRoot)
  const store = createSessionLogReceiptStore(agent.session)
  await rehydrateMemoryReceipts(store, agent.session)
  const service = new ProjectMemoryService(spec, store)

  const writeFacts = write.facts
  const projectNoteId = writeFacts.appends.project.noteId
  const userNoteId = writeFacts.appends.user.noteId
  const projectRead = await service.read({ scope: 'project', noteId: projectNoteId })
  const userRead = await service.read({ scope: 'user', noteId: userNoteId })
  const projectSearch = await service.search({ scope: 'project', query: 'acceptance note' })
  const userSearch = await service.search({ scope: 'user', query: 'acceptance preference' })
  const retryAppend = await service.append(PROJECT_NOTE)

  const mdFiles = []
  const vaultExists = existsSync(vaultRoot)
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) walk(path)
      else if (entry.name.endsWith('.md')) mdFiles.push(path)
    }
  }
  if (vaultExists) walk(vaultRoot)
  await writeTextOut(
    outDir,
    's7/vault-listing.txt',
    `${vaultRoot}\n${vaultExists ? '' : '<vault root missing>'}${mdFiles.join('\n')}\n`,
  )
  await handle.dispose()
  await ctx.fiber.dispose()

  const fieldEqual = (note, request, namespace) => note !== undefined
    && note.noteId === (namespace === 'project' ? projectNoteId : userNoteId)
    && note.body === request.body
    && note.kind === request.kind
    && note.status === request.assertionStatus
    && note.source === request.sourceRef
    && note.namespace === namespace
  const projectNote = projectRead.status === 'found' ? projectRead.note : undefined
  const userNote = userRead.status === 'found' ? userRead.note : undefined
  const projectVerified = projectRead.status === 'found' ? projectRead.verified : undefined
  const userVerified = userRead.status === 'found' ? userRead.verified : undefined

  await writeJsonOut(outDir, 's7/read.json', {
    exitcode: 0,
    reads: { project: projectRead, user: userRead },
    searches: { project: projectSearch, user: userSearch },
    retryAppend,
    mdFiles,
  })

  const verdict = assembleVerdict({
    scenario: 's7-memory-cold',
    checks: [
      ...(write.verdict === 'PASS' ? [] : [{
        id: 's7-write-phase',
        expectation: 'the write phase reproduced its checks',
        pass: false,
        observed: { writeVerdict: write.verdict },
        evidence: 's7/write.json',
      }]),
      check({
        id: 's7-read-found-verified-equal',
        expectation: 'read by noteId → found + verified:true + note fields equal the write-time request (project and user domain)',
        pass: projectRead.status === 'found' && projectVerified === true && fieldEqual(projectNote, PROJECT_NOTE, 'projects/ws-accept')
          && userRead.status === 'found' && userVerified === true && fieldEqual(userNote, USER_NOTE, 'user'),
        observed: {
          project: { status: projectRead.status, verified: projectVerified, note: projectNote },
          user: { status: userRead.status, verified: userVerified, note: userNote },
        },
        evidence: 's7/read.json',
      }),
      check({
        id: 's7-search-one-hit-per-domain',
        expectation: 'search hits exactly one note in each domain',
        pass: projectSearch.hits.length === 1 && userSearch.hits.length === 1,
        observed: { projectHits: projectSearch.hits, userHits: userSearch.hits },
        evidence: 's7/read.json',
      }),
      check({
        id: 's7-retry-append-already-exists',
        expectation: 'retrying the same append (same sourceRef) reports already_exists',
        pass: retryAppend.status === 'already_exists',
        observed: retryAppend,
        evidence: 's7/read.json',
      }),
      check({
        id: 's7-vault-two-real-md-files',
        expectation: 'exactly two real .md files exist inside the Vault (one per domain)',
        pass: mdFiles.length === 2,
        observed: { mdFiles },
        evidence: 's7/vault-listing.txt',
      }),
    ],
    notes: [
      'read 进程经 ctx.agents.resume 冷加载后先 rehydrateMemoryReceipts 再以新 ProjectMemoryService（同 Vault 同 spec）读回',
      'ctx.agents.resume 传入与 write 相同的 agentOptions（provider/model 路由一致）—— 已登记偏差（design 文本仅列 resumeSessionId）',
    ],
  })
  await writeVerdict(outDir, verdict)
  return exitCodeForVerdict(verdict)
}

const parsed = parseCliArgs(
  process.argv.slice(2),
  { tree: { required: true }, out: { required: true }, phase: { required: true }, root: { required: true } },
  USAGE,
)
const runner = parsed.phase === 'write'
  ? runWrite(parsed.root, parsed.out)
  : parsed.phase === 'read'
    ? runRead(parsed.root, parsed.out)
    : Promise.reject(new Error(`--phase must be write|read, got "${parsed.phase}". ${USAGE}`))
process.exit(await runner.catch(error => recordHarnessError(parsed.out, 's7-memory-cold', error)))
