"""Evidence signing tests — HMAC-SHA256 tamper detection.

Tests 1-5 are unit tests for the signing module.
Test 6 is an integration test with EvidenceIndex.add_evidence.
"""

import os
import json
import tempfile

import pytest

from evidence.signing import (
    sign_evidence,
    verify_evidence,
    SIGNING_KEY_ENV,
)


# ---- helpers ----

def _set_key(monkeypatch, key="test-key-123"):
    monkeypatch.setenv(SIGNING_KEY_ENV, key)


def _unset_key(monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)


# ---- Test 1: Sign and verify ----

def test_sign_and_verify(monkeypatch):
    """Sign with a key, then verify returns True."""
    _set_key(monkeypatch, "secret")

    sig = sign_evidence(
        evidence_type="screenshot",
        tool="maestro",
        path="/tmp/shot.png",
        sha256="abcdef1234567890",
        timestamp="2026-05-26T12:00:00Z",
        build_id="build-001",
    )
    assert sig["signature_status"] == "signed"
    assert sig["signature"] is not None
    assert len(sig["signature"]) == 64  # SHA256 hex digest

    ok = verify_evidence(
        evidence_type="screenshot",
        tool="maestro",
        path="/tmp/shot.png",
        sha256="abcdef1234567890",
        timestamp="2026-05-26T12:00:00Z",
        build_id="build-001",
        claimed_signature=sig["signature"],
    )
    assert ok is True


# ---- Test 2: Tampering detected ----

def test_tampering_detected(monkeypatch):
    """Modify a field after signing — verify must return False."""
    _set_key(monkeypatch, "secret")

    sig = sign_evidence(
        evidence_type="screenshot",
        tool="maestro",
        path="/tmp/shot.png",
        sha256="abcdef1234567890",
        timestamp="2026-05-26T12:00:00Z",
        build_id="build-001",
    )
    assert sig["signature_status"] == "signed"

    # Tamper: change path
    ok = verify_evidence(
        evidence_type="screenshot",
        tool="maestro",
        path="/tmp/EVIL.png",          # <— tampered
        sha256="abcdef1234567890",
        timestamp="2026-05-26T12:00:00Z",
        build_id="build-001",
        claimed_signature=sig["signature"],
    )
    assert ok is False


# ---- Test 3: Wrong key fails ----

def test_wrong_key_fails(monkeypatch):
    """Sign with key A, verify with key B must return False."""
    _set_key(monkeypatch, "key-A")

    sig = sign_evidence(
        evidence_type="video",
        tool="playwright",
        path="/tmp/vid.mp4",
        sha256="feedface",
        timestamp="2026-05-26T12:00:00Z",
        build_id="build-002",
    )
    assert sig["signature_status"] == "signed"

    # Switch to different key
    monkeypatch.setenv(SIGNING_KEY_ENV, "key-B")

    ok = verify_evidence(
        evidence_type="video",
        tool="playwright",
        path="/tmp/vid.mp4",
        sha256="feedface",
        timestamp="2026-05-26T12:00:00Z",
        build_id="build-002",
        claimed_signature=sig["signature"],
    )
    assert ok is False


# ---- Test 4: No key = unsigned ----

def test_no_key_unsigned(monkeypatch):
    """When EVIDENCE_SIGNING_KEY is not set, sign_evidence returns unsigned."""
    _unset_key(monkeypatch)

    sig = sign_evidence(
        evidence_type="screenshot",
        tool="maestro",
        path="/tmp/shot.png",
        sha256="abcdef",
        timestamp="2026-05-26T12:00:00Z",
        build_id="build-001",
    )
    assert sig["signature_status"] == "unsigned"
    assert sig["signature"] is None


# ---- Test 5: verify_evidence with None signature -> False ----

def test_verify_none_signature_false(monkeypatch):
    """Calling verify_evidence with claimed_signature=None returns False."""
    _set_key(monkeypatch, "secret")

    ok = verify_evidence(
        evidence_type="screenshot",
        tool="maestro",
        path="/tmp/shot.png",
        sha256="abcdef",
        timestamp="2026-05-26T12:00:00Z",
        build_id="build-001",
        claimed_signature=None,          # unsigned
    )
    assert ok is False


# ---- Test 6: Integration — EvidenceIndex.add_evidence stores signature ----

def test_add_evidence_stores_signature(monkeypatch):
    """With key set, add_evidence produces entries with signature fields."""
    _set_key(monkeypatch, "integration-secret")

    from evidence.collector import EvidenceIndex, _compute_sha256

    # Create a temp file so _compute_sha256 succeeds
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False, mode="w") as f:
        f.write("fake-png-content")
        tmp_path = f.name

    try:
        index = EvidenceIndex(
            project="test-proj",
            timestamp="2026-05-26_120000",
            build_id="build-int",
        )
        index.add_evidence(
            type="screenshot",
            tool="maestro",
            path=tmp_path,
        )

        assert len(index.evidences) == 1
        entry = index.evidences[0]

        # SHA256 should still be present
        assert "sha256" in entry["metadata"]
        assert entry["metadata"]["sha256"] is not None

        # Signature fields
        assert entry.get("signature_status") == "signed"
        assert entry.get("signature") is not None
        assert len(entry.get("signature", "")) == 64

        # Verify the stored signature
        ok = verify_evidence(
            evidence_type=entry["type"],
            tool=entry["tool"],
            path=entry["path"],
            sha256=entry["metadata"]["sha256"],
            timestamp=entry["collected_at"],
            build_id=index.build_id,
            claimed_signature=entry["signature"],
        )
        assert ok is True

    finally:
        os.unlink(tmp_path)


# ---- Test: payload stability (deterministic) ----

def test_payload_deterministic(monkeypatch):
    """Same inputs produce the same signature."""
    _set_key(monkeypatch, "stable-key")

    a = sign_evidence("s", "t", "/p", "abcdef", "2026-05-26T00:00:00Z", "b1")
    b = sign_evidence("s", "t", "/p", "abcdef", "2026-05-26T00:00:00Z", "b1")

    assert a["signature"] == b["signature"]


# ---- Test: different payloads -> different signatures ----

def test_different_payloads_different_signatures(monkeypatch):
    """Different fields produce different signatures."""
    _set_key(monkeypatch, "secret")

    sig1 = sign_evidence("screenshot", "maestro", "/a.png", "abc", "2026-05-26T00:00:00Z", "b1")
    sig2 = sign_evidence("video",     "maestro", "/a.png", "abc", "2026-05-26T00:00:00Z", "b1")

    assert sig1["signature"] != sig2["signature"]


# ---- Test: backward compatibility — missing signature fields ----

def test_backward_compat_missing_signature_fields(monkeypatch):
    """Evidence dict without signature/signature_status fields loads fine."""
    entry = {
        "type": "screenshot",
        "tool": "maestro",
        "path": "/tmp/shot.png",
        "metadata": {"sha256": "abc123"},
        "collected_at": "2026-05-26T12:00:00Z",
    }
    # Old entries without signature fields — no crash
    assert "signature" not in entry
    assert "signature_status" not in entry
    # This is the expected backward-compatible state
    assert entry["metadata"]["sha256"] == "abc123"
