"""Unit tests for evidence collector: SHA256 integrity checksum."""

import os
import tempfile
import hashlib
import pytest

from evidence.collector import _compute_sha256


class TestSHA256Integrity:
    def test_known_content(self):
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
            f.write(b"hello evidence world")
            path = f.name
        try:
            expected = hashlib.sha256(b"hello evidence world").hexdigest()
            result = _compute_sha256(path)
            assert result == expected
        finally:
            os.unlink(path)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
            path = f.name
        try:
            expected = hashlib.sha256(b"").hexdigest()
            result = _compute_sha256(path)
            assert result == expected
        finally:
            os.unlink(path)

    def test_binary_content(self):
        data = bytes(range(256)) * 10
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
            f.write(data)
            path = f.name
        try:
            expected = hashlib.sha256(data).hexdigest()
            result = _compute_sha256(path)
            assert result == expected
        finally:
            os.unlink(path)

    def test_file_not_found_returns_none(self):
        result = _compute_sha256("/nonexistent/path/abc123.xyz")
        assert result is None

    def test_directory_path_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _compute_sha256(tmp)
            assert result is None

    def test_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
            f.write(b"deterministic test content")
            path = f.name
        try:
            r1 = _compute_sha256(path)
            r2 = _compute_sha256(path)
            assert r1 == r2
            assert r1 is not None
        finally:
            os.unlink(path)

    def test_large_file(self):
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
            f.write(b"x" * 1_000_000)
            path = f.name
        try:
            expected = hashlib.sha256(b"x" * 1_000_000).hexdigest()
            result = _compute_sha256(path)
            assert result == expected
        finally:
            os.unlink(path)
