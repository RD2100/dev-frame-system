/** The reference subprocess execution face: exact commands, honest outcomes, config-order echoes. */

import { tmpdir } from 'node:os'
import { expect, it } from 'vitest'
import { createSubprocessRequiredChecksExecution, subprocessRequiredChecksExecution } from '../src/check-runner.ts'
import type { DevFrameRequiredCheck, DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'

/** The working directory echoed by the first fixture check (a real directory). */
const CWD_A = tmpdir()
/** The working directory echoed by the second fixture check (a real directory). */
const CWD_B = process.cwd()

/** One config with the given checks, in the exact shape the store would return. */
function configOf(checks: readonly DevFrameRequiredCheck[]): DevFrameRequiredChecksConfig {
  return { version: 1, checks }
}

it('records a passing check with exit code 0 and the verbatim command identity', async () => {
  const execution = createSubprocessRequiredChecksExecution()
  const config = configOf([{
    checkId: 'check-pass',
    executable: process.execPath,
    arguments: ['-e', 'process.exit(0)'],
    cwd: CWD_A,
  }])

  const [result] = await execution(config)

  expect(result).toMatchObject({
    checkId: 'check-pass',
    executable: process.execPath,
    arguments: ['-e', 'process.exit(0)'],
    cwd: CWD_A,
    status: 'passed',
    exitCode: 0,
  })
  expect(result?.durationMs).toBeGreaterThanOrEqual(0)
})

it('records a failing check with its real non-zero exit code as failed evidence', async () => {
  const config = configOf([{
    checkId: 'check-fail',
    executable: process.execPath,
    arguments: ['-e', 'process.exit(3)'],
    cwd: CWD_B,
  }])

  const [result] = await subprocessRequiredChecksExecution(config)

  expect(result).toMatchObject({
    checkId: 'check-fail',
    executable: process.execPath,
    arguments: ['-e', 'process.exit(3)'],
    cwd: CWD_B,
    status: 'failed',
    exitCode: 3,
  })
})

it('classifies a check killed by the wall-clock guard as timed_out without an exit code', async () => {
  const execution = createSubprocessRequiredChecksExecution({ timeoutMs: 50 })
  const config = configOf([{
    checkId: 'check-hang',
    executable: process.execPath,
    arguments: ['-e', 'setTimeout(() => {}, 10_000)'],
    cwd: CWD_A,
  }])

  const [result] = await execution(config)

  expect(result).toMatchObject({ checkId: 'check-hang', status: 'timed_out' })
  expect(Object.hasOwn(result ?? {}, 'exitCode')).toBe(false)
  expect(result?.durationMs).toBeGreaterThanOrEqual(0)
})

it('classifies a rejection without an exit code, such as a missing executable, as unknown', async () => {
  const execution = createSubprocessRequiredChecksExecution()
  const config = configOf([{
    checkId: 'check-missing',
    executable: 'dsh-evjournal-no-such-executable',
    arguments: [],
    cwd: CWD_A,
  }])

  const [result] = await execution(config)

  expect(result).toMatchObject({ checkId: 'check-missing', status: 'unknown' })
  expect(Object.hasOwn(result ?? {}, 'exitCode')).toBe(false)
})

it('runs every configured check in config order and echoes each command identity verbatim', async () => {
  const execution = createSubprocessRequiredChecksExecution()
  const config = configOf([
    { checkId: 'check-a', executable: process.execPath, arguments: ['-e', 'process.exit(0)'], cwd: CWD_A },
    { checkId: 'check-b', executable: process.execPath, arguments: ['-e', 'process.exit(2)'], cwd: CWD_B },
    { checkId: 'check-c', executable: process.execPath, arguments: ['-e', 'process.exit(0)'], cwd: CWD_B },
  ])

  const results = await execution(config)

  expect(results.map(result => result.checkId)).toEqual(['check-a', 'check-b', 'check-c'])
  expect(results.map(result => result.status)).toEqual(['passed', 'failed', 'passed'])
  expect(results.map(result => [result.executable, result.arguments, result.cwd])).toEqual([
    [process.execPath, ['-e', 'process.exit(0)'], CWD_A],
    [process.execPath, ['-e', 'process.exit(2)'], CWD_B],
    [process.execPath, ['-e', 'process.exit(0)'], CWD_B],
  ])
})
