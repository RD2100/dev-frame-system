/**
 * File-backed {@link RequiredChecksConfigStore} reference implementation: the
 * digest → configuration registrations persist as one JSON ledger whose path
 * the host Config supplies, so an approved checklist outlives the process
 * that registered it.
 *
 * The ledger is the untrusted durable boundary and is validated wholesale on
 * every read: unparseable bytes, a wrong envelope (including a future
 * `version`), and a registration whose digest disagrees with its own
 * configuration's canonical digest all fail loud with
 * `REQUIRED_CHECKS_STORE_CORRUPT`, while a registered configuration payload
 * failing its schema keeps the interface-mandated
 * `REQUIRED_CHECKS_INVALID_CONFIG` from {@link decodeRequiredChecksConfig}. A
 * missing ledger is no registrations (`REQUIRED_CHECKS_CONFIG_NOT_FOUND`),
 * never a fallback configuration. Publishes go through a same-directory temp
 * file + rename, so a reader sees the old or the new complete ledger and
 * never a torn one; there are no locks, so the store assumes a single writer
 * and concurrent writers are last-writer-wins. This is an injectable
 * alternative to {@link MemoryRequiredChecksConfigStore}. Host command,
 * delivery, and integration plugins select the ledger through their Config.
 * @module @deepseek-ai/dsh-experimental-devframe/required-checks-file-store
 */

import { randomBytes } from 'node:crypto'
import { readFile, rename, writeFile } from 'node:fs/promises'
import { z } from 'zod'
import {
  decodeRequiredChecksConfig,
  type DevFrameRequiredChecksConfig,
  type RequiredChecksConfigStore,
  RequiredChecksError,
  type RequiredChecksDigest,
  requiredChecksDigest,
} from './required-checks.ts'

/** Ledger format generation; a ledger written by another generation fails loud. */
const LEDGER_VERSION = 1

/** Canonical shape of a registered digest, mirroring {@link requiredChecksDigest}'s output. */
const LEDGER_DIGEST_SCHEMA = z.string().regex(/^dsh-required-checks-v1-[0-9a-f]{64}$/)

const ledgerRegistrationSchema = z.object({
  digest: LEDGER_DIGEST_SCHEMA,
  // The registered configuration is deliberately opaque at the envelope:
  // its schema failures must surface as REQUIRED_CHECKS_INVALID_CONFIG from
  // decodeRequiredChecksConfig (the store contract), not as ledger corruption.
  config: z.unknown(),
}).strict()

const ledgerSchema = z.object({
  version: z.literal(LEDGER_VERSION),
  registrations: z.array(ledgerRegistrationSchema),
}).strict()

/** One wholesale-validated ledger registration. */
interface LedgerRegistration {
  readonly digest: string
  readonly config: DevFrameRequiredChecksConfig
}

/** The parsed-and-validated ledger document every read and write builds on. */
interface ValidatedLedger {
  readonly registrations: readonly LedgerRegistration[]
}

/**
 * Parse raw ledger bytes into the wholesale-validated form: every
 * registration is schema-decoded and digest-checked before any lookup runs,
 * so corruption anywhere fails every load and save regardless of which
 * digest is requested.
 * @param raw - ledger bytes read as UTF-8 text.
 * @param path - ledger path named in the fail-loud messages.
 * @returns the validated registrations in file order.
 * @throws {@link RequiredChecksError} with `REQUIRED_CHECKS_STORE_CORRUPT`
 *   when the bytes are not JSON or fail the ledger envelope, with
 *   `REQUIRED_CHECKS_INVALID_CONFIG` when a registered configuration payload
 *   fails its schema, and with `REQUIRED_CHECKS_STORE_CORRUPT` when a
 *   registration's digest disagrees with its configuration's canonical digest.
 */
function parseLedger(raw: string, path: string): ValidatedLedger {
  let document: unknown
  try {
    document = JSON.parse(raw)
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    throw new RequiredChecksError(
      `required-checks registration ledger "${path}" is corrupt: not valid JSON (${reason})`,
      'REQUIRED_CHECKS_STORE_CORRUPT',
      { cause: error },
    )
  }
  const envelope = ledgerSchema.safeParse(document)
  if (!envelope.success) {
    const summary = envelope.error.issues
      .map(issue => `${issue.path.map(String).join('.') || '(root)'}: ${issue.message}`)
      .join('; ')
    throw new RequiredChecksError(
      `required-checks registration ledger "${path}" is corrupt: ${summary}`,
      'REQUIRED_CHECKS_STORE_CORRUPT',
      { cause: envelope.error },
    )
  }
  const registrations: LedgerRegistration[] = []
  for (const [index, entry] of envelope.data.registrations.entries()) {
    const config = decodeRequiredChecksConfig(entry.config)
    const actual = requiredChecksDigest(config)
    if (entry.digest !== actual) {
      throw new RequiredChecksError(
        `required-checks registration ledger "${path}" is corrupt: registration ${index} claims digest "${entry.digest}" but its configuration digests to "${actual}"`,
        'REQUIRED_CHECKS_STORE_CORRUPT',
      )
    }
    registrations.push({ digest: entry.digest, config })
  }
  return { registrations }
}

/**
 * Read and wholesale-validate the ledger, treating an absent file as no
 * registrations so a first save does not need the ledger to pre-exist.
 * @param path - ledger path from the store Config.
 * @returns the validated ledger, or `undefined` when the file does not exist.
 * @throws raw fs errors other than ENOENT, unwrapped.
 * @throws {@link RequiredChecksError} per {@link parseLedger}.
 */
async function readLedger(path: string): Promise<ValidatedLedger | undefined> {
  let raw: string
  try {
    raw = await readFile(path, 'utf8')
  } catch (error) {
    // ENOENT is absence (no registrations yet); every other fs failure is a
    // real IO error rethrown raw so its true cause reaches the caller.
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined
    throw error
  }
  return parseLedger(raw, path)
}

/** Host-supplied settings for the file-backed required-checks registration store. */
export interface FileRequiredChecksConfigStoreOptions {
  /**
   * Path of the JSON registration ledger, used exactly as given. Created by
   * the first `save`; the parent directory must already exist (a missing
   * directory fails save loud with the raw fs error).
   */
  readonly path: string
}

/**
 * File-backed durable {@link RequiredChecksConfigStore} reference
 * implementation: registrations persist as one JSON ledger at the
 * Config-supplied path and every read validates the whole document (the
 * failure routing is documented on the module). Publishes replace the ledger
 * via a same-directory temp file + rename, so a concurrent reader sees the
 * old or the new complete ledger; there are no locks, so the store assumes a
 * single writer and concurrent writers are last-writer-wins. An injectable
 * alternative to {@link MemoryRequiredChecksConfigStore}; the deployment must
 * own the ledger path and serialize registration writes.
 */
export class FileRequiredChecksConfigStore implements RequiredChecksConfigStore {
  private readonly ledgerPath: string

  /**
   * @param options - host-resolved store settings; `options.path` is the
   *   ledger location used exactly as given.
   */
  constructor(options: FileRequiredChecksConfigStoreOptions) {
    this.ledgerPath = options.path
  }

  /**
   * Register one approved configuration under its canonical digest,
   * persisting the ledger. A configuration whose digest is already present
   * is the same registration: the ledger is left untouched and the existing
   * digest is returned.
   * @param config - validated configuration from the typed approval boundary.
   * @returns the digest the configuration is registered under.
   * @throws {@link RequiredChecksError} with `REQUIRED_CHECKS_STORE_CORRUPT`
   *   when the existing ledger is corrupt — save never repairs or overwrites
   *   corruption. Raw fs errors (e.g. a missing parent directory) propagate
   *   unwrapped.
   */
  async save(config: DevFrameRequiredChecksConfig): Promise<RequiredChecksDigest> {
    const digest = requiredChecksDigest(config)
    const ledger = await readLedger(this.ledgerPath)
    const registrations = ledger?.registrations ?? []
    if (registrations.some(registration => registration.digest === digest)) {
      return digest
    }
    const document = {
      version: LEDGER_VERSION,
      registrations: [...registrations, { digest, config }],
    }
    const tempPath = `${this.ledgerPath}.${randomBytes(6).toString('hex')}.tmp`
    await writeFile(tempPath, `${JSON.stringify(document, null, 2)}\n`, 'utf8')
    await rename(tempPath, this.ledgerPath)
    return digest
  }

  /**
   * Resolve one digest to its registered configuration, reading and
   * validating the whole ledger first.
   * @param digest - canonical identity recorded at approval time.
   * @returns the validated registered configuration.
   * @throws {@link RequiredChecksError} with `REQUIRED_CHECKS_CONFIG_NOT_FOUND`
   *   when the ledger does not exist or registers no configuration under the
   *   digest, `REQUIRED_CHECKS_INVALID_CONFIG` when a registered payload
   *   fails its schema, and `REQUIRED_CHECKS_STORE_CORRUPT` when the ledger
   *   is unreadable as the expected document. Non-ENOENT fs errors propagate
   *   unwrapped.
   */
  async load(digest: RequiredChecksDigest): Promise<DevFrameRequiredChecksConfig> {
    const ledger = await readLedger(this.ledgerPath)
    const registration = ledger?.registrations.find(entry => entry.digest === digest)
    if (registration === undefined) {
      throw new RequiredChecksError(
        `no required-checks configuration is registered under "${digest}" (registration ledger "${this.ledgerPath}")`,
        'REQUIRED_CHECKS_CONFIG_NOT_FOUND',
      )
    }
    return registration.config
  }
}
