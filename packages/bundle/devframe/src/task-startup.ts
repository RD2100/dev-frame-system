/**
 * DevFrame's bounded project-task command-line provider.
 *
 * The launcher keeps the ordinary Web invocation unchanged: this provider
 * publishes a value only when the inner `task` command is selected.
 * @module @deepseek-ai/dsh-devframe/task-startup
 */

import { Command } from 'commander'
import type { Context } from '@deepseek-ai/cordis'
import { parseCmdline } from '@deepseek-ai/dsh-cmdline'

/** Stable Cordis plugin name. */
export const name = 'devframe-task-startup'

/** This provider only needs the launcher's immutable command-line snapshot. */
export const inject = ['cmdlineArgs']

/** Service published for the task runner when `task` was requested. */
export const DEVFRAME_TASK_STARTUP_SERVICE = 'devframeTaskStartup'

/** Explicit opt-in required for the unfinished project-task tracer. */
export const DEVFRAME_EXPERIMENTAL_TASKS_ENV = 'DSH_DEVFRAME_EXPERIMENTAL_TASKS'

/** Parsed, pathless command options handed to the task runner. */
export interface DevFrameTaskStartupValues {
  /** Workspace id or directory selector supplied by the user. */
  readonly project: string
  /** Human objective forwarded to the bounded Project Controller. */
  readonly objective: string
  /** Maximum number of native Goal Rounds requested by this invocation. */
  readonly rounds: 1 | 2
}

/**
 * Whether the unfinished task tracer was explicitly enabled by the operator.
 * The default is deliberately disabled while the permission and audit layers
 * are incomplete; this is not the DevFrame security boundary.
 * @param env - environment values to inspect.
 * @returns true only for the explicit `1` switch value.
 */
export function experimentalTasksEnabled(
  env: Readonly<Record<string, string | undefined>> = process.env,
): boolean {
  return env[DEVFRAME_EXPERIMENTAL_TASKS_ENV] === '1'
}

interface TaskOptions {
  project?: string
  objective?: string
  rounds?: string
}

/** Create a fresh command tree so tests and embedded hosts can parse repeatedly. */
function devFrameCommand(): Command {
  const program = new Command()
    .name('dsh --profile devframe')
    .description('Run one bounded DevFrame task in a registered project.')
    .helpOption('-h, --help', 'show this help')
    .addHelpText('after', `
Examples:
  dsh --profile devframe task --project . --objective "run the focused tests"
  dsh --profile devframe task --project <workspace-id> --objective "fix the failing test" --rounds 2
`)

  program
    .command('task')
    .description('dispatch one bounded project task through the DevFrame Controller')
    .requiredOption('--project <workspace-id-or-path>', 'registered workspace id or existing directory')
    .requiredOption('--objective <text>', 'bounded task objective')
    .option('--rounds <1|2>', 'maximum Goal Rounds (default: 1)', '1')
  return program
}

/**
 * Parse the app-owned task command and publish it as a normal Cordis service.
 * Only a first app argument of `task` belongs to this provider. Empty and Web
 * arguments remain owned by `dsh-web-app`; this provider must never parse or
 * reject flags such as `--port` and `--host`.
 */
export function apply(ctx: Context): void {
  const cmdline = ctx.get('cmdlineArgs')
  if (cmdline === undefined) {
    throw new Error('devframe-task-startup: the launcher must provide ctx.cmdlineArgs before the tree mounts')
  }
  if (cmdline.get()[0] !== 'task') return

  const program = devFrameCommand()
  const task = program.commands.find(command => command.name() === 'task')
  if (task === undefined) throw new Error('devframe-task-startup: task command was not registered')
  task.action((_options: TaskOptions, command: Command) => {
    if (!experimentalTasksEnabled()) {
      command.error(`error: task is experimental and disabled by default; set ${DEVFRAME_EXPERIMENTAL_TASKS_ENV}=1 to enable`)
    }
    const options = command.opts<TaskOptions>()
    const project = options.project?.trim() ?? ''
    const objective = options.objective?.trim() ?? ''
    const rounds = options.rounds?.trim() ?? '1'
    if (project === '') command.error('error: --project cannot be empty')
    if (objective === '') command.error('error: --objective cannot be empty')
    if (rounds !== '1' && rounds !== '2') {
      command.error(`error: --rounds must be 1 or 2, got ${JSON.stringify(rounds)}`)
    }
    ctx.provide(DEVFRAME_TASK_STARTUP_SERVICE, {
      project,
      objective,
      rounds: rounds === '2' ? 2 : 1,
    } satisfies DevFrameTaskStartupValues)
  })
  parseCmdline(ctx, program)
}

/** Exposed for parser tests without exposing the Host context. */
export const internals = { devFrameCommand }
