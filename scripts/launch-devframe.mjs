/**
 * Start the built DevFrame profile and open the printed loopback URL.
 *
 * This is a small Windows-friendly launcher for the desktop shortcut. It is
 * deliberately not an Electron/Tauri shell: DSH remains the normal Node CLI
 * and the browser remains the UI surface.
 */

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const CLI = join(ROOT, 'apps', 'cli', 'lib', 'bin.js')
const PORT = process.env.DSH_DESKTOP_PORT ?? '0'

/** Build the child argv used by the desktop entrypoint. */
export function buildDevFrameCliArgs(forwarded, options = {}) {
  const cli = options.cli ?? CLI
  const port = options.port ?? PORT
  const hasExplicitProfile = forwarded.some((argument) => argument === '--profile' || argument.startsWith('--profile='))
  const hasExplicitPort = forwarded.some((argument) => argument === '--port' || argument.startsWith('--port='))
  const profileArgs = hasExplicitProfile ? [] : ['--profile', 'devframe']
  const portArgs = hasExplicitPort ? [] : ['--port', port]
  // An explicit profile must remain before every app argument. When the
  // caller owns the profile, append our default Web port after its argv so a
  // launcher flag cannot turn into an app argument before `--profile`.
  return hasExplicitProfile
    ? [cli, ...forwarded, ...portArgs]
    : [cli, ...profileArgs, ...portArgs, ...forwarded]
}

/** Start the built CLI and open its loopback Web URL. */
export function runLauncher(forwarded = process.argv.slice(2)) {
  if (!existsSync(CLI)) {
    console.error(`DevFrame launcher: built CLI not found at ${CLI}`)
    console.error('Run `pnpm run build:lib:host` first, then launch again.')
    process.exitCode = 2
    return
  }

  const cliArgs = buildDevFrameCliArgs(forwarded)
  const child = spawn(process.execPath, cliArgs, {
    cwd: ROOT,
    env: process.env,
    stdio: ['inherit', 'pipe', 'inherit'],
  })

  let output = ''
  let browserOpened = false
  child.stdout.on('data', (chunk) => {
    const text = String(chunk)
    process.stdout.write(text)
    output = `${output}${text}`.slice(-8192)
    const match = output.match(/dsh web: (http:\/\/127\.0\.0\.1:\d+)/)
    if (match?.[1] !== undefined && !browserOpened) {
      browserOpened = true
      if (process.env.DSH_DESKTOP_SKIP_BROWSER !== '1') {
        const browser = spawn('explorer.exe', [match[1]], { detached: true, stdio: 'ignore' })
        browser.unref()
      }
    }
  })

  child.on('error', (error) => {
    console.error(`DevFrame launcher: ${error.message}`)
    process.exitCode = 1
  })

  child.on('exit', (code, signal) => {
    process.exit(signal === null ? code ?? 1 : 1)
  })
}

if (process.argv[1] !== undefined && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runLauncher()
}
