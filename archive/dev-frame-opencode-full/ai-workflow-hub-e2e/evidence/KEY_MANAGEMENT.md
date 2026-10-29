# Evidence Signing Key Management

> Status: Design document
> Phase: Maintenance 1 Batch D — production-grade key management plan
> Date: 2026-05-26
> Executor: Executor-D-SigningProductionPlan

## Current State

The evidence signing module (`evidence/signing.py`) uses HMAC-SHA256 with a single
symmetric key read from the environment variable `EVIDENCE_SIGNING_KEY`.

```
sign_evidence(payload) → HMAC-SHA256(payload, key) → hex digest
verify_evidence(payload, claimed_hohohmac) → compare_digest(recompute, claimed)
```

Each evidence item in the index stores:
```json
{
  "signature": "<hex digest>",
  "signature_status": "signed" | "unsigned"
}
```

**Sufficient for local CI** — a single trusted pipeline owns both signing and
verification.  However, the flat-key design has known gaps that limit
production readiness:

| Gap | Impact |
|-----|--------|
| No key versioning | Key rotation invalidates all old evidence |
| Single key | All projects/environments share the same key with no isolation |
| No key lookup metadata | Verifier cannot determine which key signed an item |
| HMAC only | Symmetric: anyone with the key can forge (no non-repudiation) |

## Proposed: Key Versioning

### Key ID Format

```
"v{serial}"    e.g. "v1", "v2", "v3"
```

- Monotonically increasing integer.
- Concise, sortable, human-readable.
- Avoids date-based IDs (which break when multiple keys are created in one day)
  and environment-prefixed IDs (which couple the key to a deployment target).

### Where Stored

The `key_id` is added to each evidence item alongside the signature:

```json
{
  "signature": "<hex digest>",
  "signature_status": "signed",
  "signature_key_id": "v1"
}
```

When `signature_status` is `"unsigned"`, the `signature_key_id` field is absent
(not `null` — absent means "not applicable").

### Key Store Structure

The key store is a dictionary mapping `key_id` to `key_value`:

```python
# Conceptual — not local file storage, see Key Source Hierarchy below
key_store: dict[str, str] = {
    "v1": "<key material for v1>",
    "v2": "<key material for v2>",
    "v3": "<current active key>",
}
```

Multiple keys are retained simultaneously so that old evidence can still be
verified after rotation.  Only the latest key is used for signing new
evidence.

### Which Key is "Current"

The "current" key is the one with the highest serial number.  This is
deterministic without needing a separate config flag: `max(key_store.keys())`.

### Verification Flow

```
verify_evidence(item):
    key_id = item.get("signature_key_id")   # may be absent for unsigned items

    if key_id is not None and key_id in key_store:
        primary = key_store[key_id]            # (1) Try the key_id's key
        if hmac.compare_digest(recompute(item, primary), item.signature):
            return True

    current_id = max(key_store.keys())         # (2) Fall back to current key
    fallback = key_store[current_id]
    return hmac.compare_digest(recompute(item, fallback), item.signature)
```

Rationale for the two-tier lookup:

- **Tier 1** (key_id match): The fast path.  Most evidence was signed with the
  key recorded in its metadata.
- **Tier 2** (current-key fallback): Handles the transition window — evidence
  signed just before a rotation may lack a key_id or was signed with the new
  key before the key_id convention was updated.  Also provides backward
  compatibility for evidence signed without a key_id field (legacy).

## Proposed: Key Rotation

### Rotation Policy

| Event | Action |
|-------|--------|
| New key activated | Set `EVIDENCE_SIGNING_KEY` to the new key value AND register it in the key store as the next serial (e.g., `v2`, `v3`). |
| New evidence signed | Always signed with the **current** (highest-serial) key. |
| Old evidence verified | Verified against the key identified by its `signature_key_id`. |
| Key retired | Old key remains in the store for verification; NOT used for signing. |
| Key deleted | Removed from the store after the grace period expires. |

### Grace Period

Default: **90 days**.

- Old keys are retained for 90 days after they are superseded.
- After 90 days, the key is removed from the store.
- Evidence older than 90 days with a retired key_id will fail verification
  after the key is removed.  This is acceptable: such evidence is beyond the
  retention window and should not be relied upon for audit purposes.
- The grace period is configurable via `EVIDENCE_KEY_GRACE_DAYS` (default 90).

### Old Evidence Handling

- Evidence items carry their `signature_key_id` permanently.  No re-signing is
  needed.
- When a verifier encounters evidence signed with a retired key that is still
  within the grace period, it finds the key in the store and verifies normally.
- When a verifier encounters evidence signed with a key that has been fully
  deleted (beyond grace), it returns `signature_key_unknown = True` in the
  verification result, allowing consumers to decide whether to treat it as
  untrusted or to accept it with a warning.

### Rollback Handling

If a key rollback is needed (e.g., new key was compromised or misconfigured):
- Revert `EVIDENCE_SIGNING_KEY` to the previous value.
- Old key already exists in the store (within grace period), so old evidence
  continues to verify.
- The rolled-back key resumes as the signing key for new evidence.
- The compromised key should be removed from the store immediately (grace=0).

## Proposed: Key Source Hierarchy

Keys are resolved in priority order.  Each source provides one or more
`(key_id, key_value)` pairs.

### Priority 1: Environment Variable (highest priority)

```
EVIDENCE_SIGNING_KEY=v1:<hex-encoded-key-material>
```

One key per env var.  The format is `key_id:key_value` separated by the first
colon.

For the current single-key deployment, `key_id` is optional — if omitted, the
key is auto-assigned `"v1"`:

```
EVIDENCE_SIGNING_KEY=<hex-encoded-key-material>   # → key_id="v1"
```

Multiple keys (for rotation) are provided via multiple env vars with a naming
convention:

```
EVIDENCE_SIGNING_KEY_v1=<hex>
EVIDENCE_SIGNING_KEY_v2=<hex>
EVIDENCE_SIGNING_KEY_CURRENT=v2
```

Or, more practically, via a single env var with comma- or newline-separated
entries:

```
EVIDENCE_SIGNING_KEY_STORE=v1:<hex>,v2:<hex>,v3:<hex>
```

This is the primary source for CI environments where secrets are injected via
the CI platform's secret manager (GitHub Actions secrets, GitLab CI variables,
etc.).

### Priority 2: Local Config File (development)

```
.evidence_keys.yaml   (gitignored)
```

Format:
```yaml
keys:
  v1: "<hex-encoded-key-material>"
  v2: "<hex-encoded-key-material>"
current_key_id: "v2"
grace_days: 90
```

- Located in the project root.
- Always added to `.gitignore` — must NEVER be committed.
- Used for local development and testing.
- Fallback when env var is not set.

### Priority 3: KMS / Vault (future, not implemented)

```
# Future: AWS KMS, HashiCorp Vault, Azure Key Vault, GCP KMS
```

- Lowest priority — checked only when neither env var nor config file provides
  keys.
- Provides hardware-backed key storage, audit logging, and access control.
- Out of scope for this maintenance phase.  Noted here as a design placeholder
  so the resolution order is documented.

### Resolution Algorithm

```python
def resolve_keys() -> dict[str, str]:
    # 1. Environment variable
    store = _try_env_var()
    if store:
        return store

    # 2. Local config file
    store = _try_config_file()
    if store:
        return store

    # 3. Future: KMS
    # store = _try_kms()
    # if store:
    #     return store

    return {}  # unsigned mode — no keys available
```

## Boundaries

### What This Design Provides

| Capability | Mechanism |
|------------|-----------|
| Tamper detection | HMAC-SHA256 — detects if evidence content was modified after signing |
| Key versioning | `key_id` in evidence metadata enables co-existence of old and new keys |
| Key rotation without evidence invalidation | Multiple keys retained in store; old evidence keeps its key_id |
| Graceful degradation | Unsigned mode when no keys are available |
| Multiple key sources | Env var > config file > future KMS |
| Configurable retention | Grace period for retired keys |

### What This Design Does NOT Provide

| Limitation | Why | Future Option |
|------------|-----|---------------|
| **Non-repudiation** | HMAC is symmetric — anyone with the key can forge evidence. Cannot prove WHO signed something, only that it has not been tampered with by someone without the key. | Asymmetric signatures: Ed25519, ECDSA, or RSA-PSS. The signer holds a private key (never shared); the verifier holds the public key. This proves the signer's identity. |
| **Hardware-backed key storage** | No KMS integration yet. Keys live in env vars or config files (in-memory at runtime). | KMS integration (Priority 3 above). |
| **Automatic key rotation** | Rotation is manual — operator updates the env var or config file. | Cron job or CI scheduled pipeline that generates and activates new keys. |
| **Key access audit trail** | No logging of which key was used for which operation. | KMS integration provides this natively. |
| **Distributed key agreement** | Single key store per environment. If evidence is verified by multiple consumers, they must all have the same key store. | KMS or shared vault with access-controlled key distribution. |

### Explicit Clarification: HMAC is NOT a Digital Signature

- **HMAC-SHA256** = symmetric Message Authentication Code.  Verifies that the
  message has not been tampered with by someone who does NOT possess the key.
  Does NOT identify WHO signed it.  Anyone with the key can produce a valid
  HMAC.
- **Ed25519 / ECDSA** = asymmetric digital signature.  Verifies that the
  message was signed by the holder of a specific private key.  Provides
  non-repudiation: the signer cannot later deny having signed.
- For a CI pipeline where the pipeline itself is the trusted party, HMAC is
  sufficient.  For multi-party or audit-grade evidence chains, asymmetric
  signatures are required.

## Migration Path

### From Current Flat Key to Versioned Keys

The migration is designed to be backward compatible.

**Step 1: Add key_id to evidence items (non-breaking)**

Update `sign_evidence()` and `EvidenceIndex.add_evidence()` to include
`signature_key_id` in the output.  Existing verifiers that do not look for
this field are unaffected.

**Step 2: Add key store support in sign_evidence**

`sign_evidence()` reads from the key store instead of a single env var.
Initially, the store contains one key (`v1`) which is the same key currently
in `EVIDENCE_SIGNING_KEY`.  Behavior is identical.

**Step 3: Existing evidence is verifiable via fallback**

Existing evidence items without `signature_key_id` are verified against the
current key (the only key in the store, which is the same key they were signed
with).  Verification continues to work.

**Step 4: Rotation test**

Activate `v2` alongside `v1`.  New evidence gets `key_id: "v2"`.  Old evidence
(with `key_id: "v1"` or no key_id) continues to verify against `v1` or the
fallback.  Confirm both old and new evidence verify correctly.

**Step 5: Grace period enforcement (future)**

After 90 days, remove `v1` from the store.  Evidence signed with `v1` will
return `signature_key_unknown` on verification.  This is the expected behavior
for evidence beyond the retention window.

### Backward Compatibility with Existing Unsigned Evidence

- Evidence items with `signature_status: "unsigned"` and `signature: null`
  continue to work.  No key_id is added.
- Verifiers should treat `signature_key_id` absence as "no key was used" —
  same as unsigned.
- No migration of existing evidence.json files is required.

## Stage 5+ Implementation Notes

### What Would Be Needed to Implement This

1. **Key store abstraction** (`evidence/keystore.py`):
   - `resolve_keys()` — env var, config file, future KMS.
   - `get_key(key_id)` — lookup by key_id.
   - `get_current_key_id()` — highest serial.
   - `get_current_key()` — key value for signing.

2. **Update `signing.py`**:
   - `sign_evidence()` accepts optional `key_id` and emits it in the result.
   - `verify_evidence()` accepts optional `key_id` and uses two-tier lookup.
   - `_get_key()` replaced with `_resolve_key(key_id=None)`.

3. **Update `collector.py`**:
   - `EvidenceIndex.add_evidence()` stores `signature_key_id` from sign result.

4. **Update `evidence.json` schema**:
   - Add optional `signature_key_id` field per evidence item.

5. **Tests**:
   - Unit tests for key resolution (env var, config file, fallback).
   - Unit tests for rotation (v1 → v2, both keys verify).
   - Unit tests for grace period enforcement.
   - Unit tests for backward compatibility (no key_id).

### Estimated Effort

| Component | Effort |
|-----------|--------|
| Key store (`keystore.py`) | Small (50-80 lines) |
| Update `signing.py` | Small (20-30 line diff) |
| Update `collector.py` | Trivial (1-2 line diff) |
| Tests | Medium (100-150 lines, 8-12 test cases) |
| Config file support | Small (30-40 lines, PyYAML dependency) |
| **Total** | **Small-Medium** (~1 engineering day) |

### Risks to Address Before Implementation

| Risk | Mitigation |
|------|------------|
| Key material in config file could be accidentally committed | `.evidence_keys.yaml` must be in `.gitignore`; pre-commit hook to reject files matching the pattern |
| Env var vs config file precedence confusion | Document clearly in this file; add debug logging in `resolve_keys()` showing which source was used |
| Multi-key env var format is verbose | Consider a base64-encoded JSON blob for the store; trade-off between readability and compactness |
| PyYAML dependency for config file | Alternative: use a simple `key=value` format (like `.env` files) to avoid the dependency |
| Verifier might not have all keys in the store | Document key distribution requirements; for multi-consumer setups, a shared vault is recommended |
