"""
Evidence Signing Module — HMAC-SHA256 based tamper detection.

Design
======

Key Source
----------
- The signing key is read from the environment variable ``EVIDENCE_SIGNING_KEY``.
- The key is NEVER written to disk, committed to the repo, or logged.
- In test environments, the key is set via ``monkeypatch.setenv`` or
  ``os.environ`` before the test and cleaned up afterwards.
- No external KMS / vault is required for local testing.

Signature Algorithm
-------------------
- HMAC-SHA256, using Python's standard library ``hmac`` + ``hashlib``.
- This is a symmetric MAC (Message Authentication Code), not an asymmetric
  digital signature.  It provides tamper detection but not non-repudiation,
  which is appropriate for a local CI/CD evidence chain where a single
  trusted pipeline owns both signing and verification.

Payload Format
--------------
The canonical payload is a pipe-separated ("|") concatenation of the
evidence item's identity fields:

    evidence_type|tool|path|sha256|timestamp|build_id

Example:

    screenshot|maestro|/path/to/file.png|abcdef1234|2026-05-26T00:00:00Z|build-001

- Fields are cast to ``str`` before joining; ``None`` sha256 becomes the
  literal string ``"None"``.
- The pipe character ``|`` is safe because none of the field semantics
  include pipes (evidence_type and tool are constrained alphanumeric/underscore,
  paths do not contain pipes on any target OS, hex digests do not, and
  timestamps/build_ids do not).

Verification
------------
- ``verify_evidence()`` recomputes the HMAC for the given fields and does a
  constant-time comparison (``hmac.compare_digest``) against the claimed
  signature.
- If the recomputed digest does not match, the evidence item has been
  tampered with (or the key has been rotated / is wrong).
- A ``signature`` of ``None`` always fails verification — it means the item
  was never signed.

Rotation / Revocation
---------------------
- Key rotation: change the value of ``EVIDENCE_SIGNING_KEY``.
- Old evidence signed with the old key will fail verification after rotation.
  This is intentional: the verifier must know which key to use for each item.
- For local testing this is sufficient.  In a production pipeline, key
  rotation would require versioned keys and a key index in the evidence
  metadata — out of scope for this minimal chain.

Degradation
-----------
- When ``EVIDENCE_SIGNING_KEY`` is absent (not set or empty string),
  ``sign_evidence()`` returns ``signature_status="unsigned"`` and
  ``signature=None``.
- This is explicit: "unsigned" means "we did not sign this", NOT
  "signed with an empty key".
- Downstream consumers can distinguish unsigned evidence from signed-and-
  verified evidence.

Backward Compatibility
----------------------
- Existing evidence items without ``"signature"`` and ``"signature_status"``
  fields continue to work.  Verifiers that encounter missing fields should
  treat them as unsigned.
"""

import hmac
import hashlib
import os

SIGNING_KEY_ENV = "EVIDENCE_SIGNING_KEY"


def _get_key() -> str | None:
    """Get signing key from environment. Returns None if not set."""
    val = os.environ.get(SIGNING_KEY_ENV)
    if val is None or val == "":
        return None
    return val


def _build_payload(
    evidence_type: str,
    tool: str,
    path: str,
    sha256: str | None,
    timestamp: str,
    build_id: str,
) -> str:
    """Build the canonical pipe-separated payload string."""
    sha256_str = str(sha256)  # "None" if None — canonical
    return "|".join([
        str(evidence_type),
        str(tool),
        str(path),
        sha256_str,
        str(timestamp),
        str(build_id),
    ])


def sign_evidence(
    evidence_type: str,
    tool: str,
    path: str,
    sha256: str | None,
    timestamp: str,
    build_id: str = "unknown",
) -> dict:
    """Sign an evidence item with HMAC-SHA256.

    Returns:
        {"signature": hex_digest, "signature_status": "signed"} if key is set,
        {"signature": None,     "signature_status": "unsigned"} otherwise.
    """
    key = _get_key()
    if key is None:
        return {"signature": None, "signature_status": "unsigned"}

    payload = _build_payload(evidence_type, tool, path, sha256, timestamp, build_id)
    dig = hmac.new(
        key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {"signature": dig, "signature_status": "signed"}


def verify_evidence(
    evidence_type: str,
    tool: str,
    path: str,
    sha256: str | None,
    timestamp: str,
    build_id: str,
    claimed_signature: str | None,
) -> bool:
    """Verify an HMAC signature for an evidence item.

    Returns True iff the key is available AND the recomputed HMAC matches
    ``claimed_signature`` using constant-time comparison.

    ``claimed_signature`` of ``None`` always returns False.
    """
    if claimed_signature is None:
        return False

    key = _get_key()
    if key is None:
        return False

    payload = _build_payload(evidence_type, tool, path, sha256, timestamp, build_id)
    expected = hmac.new(
        key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, claimed_signature)
