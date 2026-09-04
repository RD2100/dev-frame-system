/**
 * Create or replace one reversible Windows desktop shortcut for the local DSH
 * checkout. No registry, service, startup entry, or system-wide install is
 * performed.
 */

import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const LAUNCHER = join(ROOT, 'scripts', 'launch-devframe.mjs')
const DESKTOP = join(homedir(), 'Desktop')
const SHORTCUT = join(DESKTOP, 'DevFrame DSH.lnk')

if (process.platform !== 'win32') {
  throw new Error('create-desktop-shortcut: this helper only supports Windows.')
}
if (!existsSync(LAUNCHER)) {
  throw new Error(`create-desktop-shortcut: launcher not found at ${LAUNCHER}`)
}
mkdirSync(DESKTOP, { recursive: true })

const psQuote = (value) => `'${String(value).replaceAll("'", "''")}'`
const script = [
  '$shell = New-Object -ComObject WScript.Shell',
  `$shortcut = $shell.CreateShortcut(${psQuote(SHORTCUT)})`,
  `$shortcut.TargetPath = ${psQuote(process.execPath)}`,
  `$shortcut.Arguments = ${psQuote(`"${LAUNCHER}"`)}`,
  `$shortcut.WorkingDirectory = ${psQuote(ROOT)}`,
  `$shortcut.IconLocation = ${psQuote(`${process.execPath},0`)}`,
  `$shortcut.Description = ${psQuote('Start the local DevFrame DSH Web workspace')}`,
  '$shortcut.Save()',
].join('\n')
const encoded = Buffer.from(script, 'utf16le').toString('base64')
const result = spawnSync('powershell.exe', [
  '-NoProfile',
  '-NonInteractive',
  '-ExecutionPolicy',
  'Bypass',
  '-EncodedCommand',
  encoded,
], { encoding: 'utf8' })

if (result.error !== undefined || result.status !== 0) {
  throw new Error(`create-desktop-shortcut: PowerShell failed: ${result.error?.message ?? result.stderr.trim()}`)
}

console.log(`Created: ${SHORTCUT}`)
