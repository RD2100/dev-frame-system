/**
 * Acceptance harness session-log reader (v14-accept worker, design §1).
 *
 * Reads one multi-frame zstd JSONL session log into `{header, events[]}` with
 * every event's parsed payload preserved verbatim, reusing the repo's own
 * zstd frame reader from `packages/session/session-persistence-jsonl/src`
 * (read-session-log.mjs precedent; Node's zstdDecompressSync only reads the
 * first frame). Also locates the real per-run session directories a headless
 * run leaves under an isolated home.
 *
 * The relative import below reaches the workspace source of the harness's own
 * tree (`lib/` sits six levels below the tree root) and requires the script to
 * run under `node --import tsx/esm` with the tree's tsconfig.
 * @module harness/lib/logread
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { createZstdFrameDecoder, scanZstdFrames } from '../../../../../../packages/session/session-persistence-jsonl/src/zstd.ts'

/** Physical JSONL encodings the backend may write. */
const LOG_SUFFIXES = ['.jsonl.zstd', '.jsonl']

/**
 * Decode one session log's bytes into its header and full event list.
 * @param {string} logPath - absolute path to `session.jsonl.zstd` (or the
 *   plaintext `session.jsonl` variant).
 * @returns {{header: object, events: object[], rawText: string, frameCount: number,
 *   tornStart: number|null}} the parsed header record (the log's first line,
 *   `type: 'session'`), every event in log order, the decoded JSONL text, and
 *   the physical frame facts.
 */
export function readSessionLog(logPath) {
  const buffer = readFileSync(logPath)
  if (logPath.endsWith('.jsonl.zstd')) {
    const scan = scanZstdFrames(buffer)
    if (scan.frames.length === 0) {
      throw new Error(`readSessionLog: no complete zstd frame in "${logPath}"`)
    }
    const decoder = createZstdFrameDecoder()
    try {
      const parts = []
      for (const plaintext of decoder.decode(buffer, scan.frames)) {
        // Decoder views alias a reused buffer; copy before the next frame.
        parts.push(Buffer.from(plaintext).toString('utf8'))
      }
      return splitLog(parts.join(''), logPath, scan.frames.length, scan.tornStart ?? null)
    } finally {
      decoder.close()
    }
  }
  return splitLog(buffer.toString('utf8'), logPath, 1, null)
}

/** Split decoded JSONL text into the header record and the event list. */
function splitLog(text, logPath, frameCount, tornStart) {
  const lines = text.split('\n').filter(line => line.length > 0)
  if (lines.length === 0) throw new Error(`readSessionLog: empty session log "${logPath}"`)
  let header
  try {
    header = JSON.parse(lines[0])
  } catch (error) {
    throw new Error(`readSessionLog: header line of "${logPath}" is not JSON`, { cause: error })
  }
  const events = lines.slice(1).map((line, index) => {
    try {
      return JSON.parse(line)
    } catch (error) {
      throw new Error(`readSessionLog: event line ${index + 1} of "${logPath}" is not JSON`, { cause: error })
    }
  })
  return { header, events, rawText: text, frameCount, tornStart }
}

/**
 * Locate every real session directory a run left under a logs root, together
 * with its physical log file. For a headless run pass the run's
 * `<DSH_HOME>/sessions`; for an in-process composition pass the
 * `JsonlSessionPersistence` root directly — both use the same
 * `<project>/<session>/session.jsonl[.zstd]` layout.
 * @param {string} logsRoot - the persistence root to walk (two levels deep).
 * @returns {Array<{projectDir: string, sessionDir: string, logPath: string}>}
 *   one entry per stored session log, in directory order.
 */
export function findSessionLogs(logsRoot) {
  if (!existsSync(logsRoot)) return []
  const found = []
  for (const project of readdirSync(logsRoot, { withFileTypes: true })) {
    if (!project.isDirectory()) continue
    const projectDir = join(logsRoot, project.name)
    for (const session of readdirSync(projectDir, { withFileTypes: true })) {
      if (!session.isDirectory()) continue
      const sessionDir = join(projectDir, session.name)
      for (const suffix of LOG_SUFFIXES) {
        const logPath = join(sessionDir, `session${suffix}`)
        if (existsSync(logPath)) {
          found.push({ projectDir, sessionDir, logPath })
          break
        }
      }
    }
  }
  return found
}

/**
 * Render a readable tree listing of a logs root (evidence text form).
 * @param {string} logsRoot - root to list.
 * @returns {string} one line per directory/file with sizes, or a
 *   `<missing>` marker when the root does not exist.
 */
export function listLogsRoot(logsRoot) {
  if (!existsSync(logsRoot)) return `${logsRoot}\n<missing>\n`
  const lines = [logsRoot]
  const walk = (dir, depth) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name)
      lines.push(`${'  '.repeat(depth)}${entry.isDirectory() ? '[dir] ' : '[file]'}${entry.name}`)
      if (entry.isDirectory()) walk(path, depth + 1)
      else lines[lines.length - 1] += ` (${statSync(path).size} bytes)`
    }
  }
  walk(logsRoot, 1)
  return `${lines.join('\n')}\n`
}
