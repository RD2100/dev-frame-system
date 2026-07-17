import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema.validators import validator_for

import control_plane.rdcode_instance as rdcode_instance
from control_plane.rdcode_instance import (
    RdCodeInstanceError,
    build_rdcode_instance_spec,
    effective_rdcode_manifest_status,
    write_rdcode_instance_spec,
)
from control_plane.rdcode_runner_source import render_rdcode_instance_runner_source


REPO_ROOT = Path(__file__).resolve().parents[3]


def _t3_root(tmp_path: Path) -> Path:
    root = tmp_path / "t3code"
    (root / "apps" / "web").mkdir(parents=True)
    (root / "package.json").write_text('{"name":"t3code-test"}\n', encoding="utf-8")
    return root


def _renderer_environment(port: int) -> dict[str, str]:
    base_url = f"http://127.0.0.1:{port}"
    return {
        "VITE_DEVFRAME_REALTIME_MODE": "polling",
        "VITE_DEVFRAME_CLIENT_PLAN_URL": f"{base_url}/client-plan.json",
        "VITE_DEVFRAME_CLIENT_MANIFEST_URL": f"{base_url}/client-manifest.json",
        "VITE_HOSTED_APP_CHANNEL": "nightly",
    }


@pytest.fixture
def pinned_rdcode_tools(monkeypatch):
    tool_paths = {
        "node": "C:/tools/node.exe",
        "pnpm": "C:/tools/pnpm.cmd",
    }
    monkeypatch.setattr(rdcode_instance, "_command_path", tool_paths.get)
    monkeypatch.setattr(
        rdcode_instance,
        "_command_version",
        lambda executable, *, cwd: f"{Path(executable).stem}-test",
    )


def test_rdcode_instance_spec_is_schema_valid_and_isolated(tmp_path, pinned_rdcode_tools):
    t3_root = _t3_root(tmp_path)
    runtime_dir = tmp_path / "runtime"
    portable_pwsh = tmp_path / "powershell-portable" / "PowerShell" / "7" / "pwsh.exe"
    portable_pwsh.parent.mkdir(parents=True)
    portable_pwsh.write_bytes(b"test")

    spec = build_rdcode_instance_spec(
        runtime_dir=runtime_dir,
        t3_root=t3_root,
        host="127.0.0.1",
        control_plane_port=8788,
        renderer_environment=_renderer_environment(8788),
        instance_id="acceptance-01",
        t3_backend_port=13773,
        cdp_port=8315,
        readiness_timeout_seconds=45,
        exit_after_ready_seconds=2,
        force_build=True,
    )

    schema = json.loads(
        (REPO_ROOT / "schemas" / "rdcode_instance_spec.schema.json").read_text(encoding="utf-8")
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(spec)

    instance_dir = Path(spec["paths"]["instanceDir"])
    assert instance_dir == (runtime_dir / "rd-code" / "instances" / "acceptance-01").resolve()
    assert Path(spec["paths"]["runtimeRoot"]) == runtime_dir.resolve()
    assert Path(spec["paths"]["appDataDir"]).is_relative_to(instance_dir)
    assert Path(spec["paths"]["t3Home"]).is_relative_to(instance_dir)
    assert Path(spec["paths"]["manifestPath"]).is_relative_to(instance_dir)
    assert spec["desktopEnvironment"]["APPDATA"] == spec["paths"]["appDataDir"]
    assert spec["desktopEnvironment"]["T3CODE_HOME"] == spec["paths"]["t3Home"]
    assert spec["desktopEnvironment"]["T3CODE_PORT"] == "13773"
    assert spec["rendererEnvironment"]["VITE_DEVFRAME_CLIENT_PLAN_URL"].startswith(
        spec["controlPlane"]["baseUrl"]
    )
    assert "VITE_HOSTED_APP_CHANNEL" not in spec["rendererEnvironment"]
    assert len(spec["build"]["fingerprint"]) == 64
    assert Path(spec["tools"]["nodePath"]).name.lower() in {"node", "node.exe"}
    assert Path(spec["tools"]["pnpmPath"]).name.lower() in {"pnpm", "pnpm.cmd", "pnpm.exe", "pnpm.bat"}
    assert spec["tools"]["pwshPath"] == str(portable_pwsh.resolve())
    assert spec["launch"]["forceBuild"] is True
    assert ".electron-runtime" in Path(spec["paths"]["checkoutLockPath"]).parts
    assert "dist-electron" not in Path(spec["paths"]["checkoutLockPath"]).parts


def test_rdcode_instance_spec_rejects_unsafe_identity_and_port_collisions(tmp_path, pinned_rdcode_tools):
    t3_root = _t3_root(tmp_path)
    kwargs = {
        "runtime_dir": tmp_path / "runtime",
        "t3_root": t3_root,
        "host": "127.0.0.1",
        "control_plane_port": 8788,
        "renderer_environment": _renderer_environment(8788),
    }

    with pytest.raises(RdCodeInstanceError, match="instance_id"):
        build_rdcode_instance_spec(**kwargs, instance_id="../escape")

    with pytest.raises(RdCodeInstanceError, match="ports must be distinct"):
        build_rdcode_instance_spec(**kwargs, t3_backend_port=8788)

    with pytest.raises(RdCodeInstanceError, match="integer port"):
        build_rdcode_instance_spec(**kwargs, cdp_port=True)

    with pytest.raises(RdCodeInstanceError, match="loopback"):
        build_rdcode_instance_spec(**{**kwargs, "host": "0.0.0.0"})

    accepted = build_rdcode_instance_spec(**{**kwargs, "host": "127.0.0.2"})
    assert accepted["controlPlane"]["host"] == "127.0.0.2"


def test_rdcode_instance_fingerprint_changes_with_build_input(tmp_path, pinned_rdcode_tools):
    t3_root = _t3_root(tmp_path)
    kwargs = {
        "runtime_dir": tmp_path / "runtime",
        "t3_root": t3_root,
        "host": "127.0.0.1",
        "control_plane_port": 8788,
        "renderer_environment": _renderer_environment(8788),
    }

    first = build_rdcode_instance_spec(**kwargs)
    (t3_root / "package.json").write_text('{"name":"changed"}\n', encoding="utf-8")
    second = build_rdcode_instance_spec(**kwargs)

    assert first["build"]["sourceFingerprint"] != second["build"]["sourceFingerprint"]
    assert first["build"]["fingerprint"] != second["build"]["fingerprint"]


def test_rdcode_instance_fingerprint_tracks_all_workspace_packages(tmp_path, pinned_rdcode_tools):
    t3_root = _t3_root(tmp_path)
    kwargs = {
        "runtime_dir": tmp_path / "runtime",
        "t3_root": t3_root,
        "host": "127.0.0.1",
        "control_plane_port": 8788,
        "renderer_environment": _renderer_environment(8788),
    }

    first = build_rdcode_instance_spec(**kwargs)
    ssh_source = t3_root / "packages" / "ssh" / "src" / "client.ts"
    ssh_source.parent.mkdir(parents=True)
    ssh_source.write_text("export const sshTransport = 'changed';\n", encoding="utf-8")
    second = build_rdcode_instance_spec(**kwargs)

    assert first["build"]["sourceFingerprint"] != second["build"]["sourceFingerprint"]
    assert first["build"]["fingerprint"] != second["build"]["fingerprint"]


@pytest.mark.parametrize("host", ["::1", "0:0:0:0:0:0:0:1"])
def test_rdcode_instance_rejects_ipv6_until_dashboard_supports_it(tmp_path, host):
    with pytest.raises(RdCodeInstanceError, match="IPv4 loopback"):
        build_rdcode_instance_spec(
            runtime_dir=tmp_path / "runtime",
            t3_root=_t3_root(tmp_path),
            host=host,
            control_plane_port=8788,
            renderer_environment=_renderer_environment(8788),
        )


def test_rdcode_instance_resolves_tool_versions_in_t3_root(tmp_path, monkeypatch):
    t3_root = _t3_root(tmp_path)
    calls: list[tuple[str, Path]] = []

    monkeypatch.setattr(rdcode_instance, "_command_path", lambda command: f"C:/tools/{command}.cmd")

    def fake_version(executable: str, *, cwd: Path) -> str:
        calls.append((executable, cwd))
        return f"{Path(executable).stem}@{cwd.name}"

    monkeypatch.setattr(rdcode_instance, "_command_version", fake_version)

    spec = build_rdcode_instance_spec(
        runtime_dir=tmp_path / "runtime",
        t3_root=t3_root,
        host="127.0.0.1",
        control_plane_port=8788,
        renderer_environment=_renderer_environment(8788),
    )

    assert spec["build"]["toolchain"]["node"] == "node@t3code"
    assert spec["build"]["toolchain"]["pnpm"] == "pnpm@t3code"
    assert calls == [
        ("C:/tools/node.cmd", t3_root.resolve()),
        ("C:/tools/pnpm.cmd", t3_root.resolve()),
    ]


def test_rdcode_instance_rejects_missing_required_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(rdcode_instance, "_command_path", lambda _command: None)

    with pytest.raises(RdCodeInstanceError, match="node and pnpm must both be available on PATH"):
        build_rdcode_instance_spec(
            runtime_dir=tmp_path / "runtime",
            t3_root=_t3_root(tmp_path),
            host="127.0.0.1",
            control_plane_port=8788,
            renderer_environment=_renderer_environment(8788),
        )


def test_rdcode_instance_rejects_unreadable_pinned_tool_version(tmp_path, monkeypatch):
    monkeypatch.setattr(
        rdcode_instance.subprocess,
        "run",
        lambda *_args, **_kwargs: rdcode_instance.subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="broken tool"
        ),
    )

    with pytest.raises(RdCodeInstanceError, match="cannot read pinned tool version"):
        rdcode_instance._command_version("C:/tools/pnpm.cmd", cwd=tmp_path)


def test_write_rdcode_instance_spec_is_round_trippable(tmp_path, pinned_rdcode_tools):
    spec = build_rdcode_instance_spec(
        runtime_dir=tmp_path / "runtime",
        t3_root=_t3_root(tmp_path),
        host="127.0.0.1",
        control_plane_port=8788,
        renderer_environment=_renderer_environment(8788),
    )

    spec_path = write_rdcode_instance_spec(spec)

    assert spec_path == Path(spec["paths"]["specPath"])
    assert json.loads(spec_path.read_text(encoding="utf-8")) == spec
    assert not spec_path.with_suffix(spec_path.suffix + ".tmp").exists()


def test_write_rdcode_instance_spec_is_atomic_under_concurrent_writers(tmp_path, pinned_rdcode_tools):
    spec = build_rdcode_instance_spec(
        runtime_dir=tmp_path / "runtime",
        t3_root=_t3_root(tmp_path),
        host="127.0.0.1",
        control_plane_port=8788,
        renderer_environment=_renderer_environment(8788),
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        paths = list(executor.map(lambda _index: write_rdcode_instance_spec(spec), range(24)))

    assert len(set(paths)) == 1
    assert json.loads(paths[0].read_text(encoding="utf-8")) == spec
    assert list(paths[0].parent.glob("*.tmp")) == []


def test_effective_manifest_status_expires_a_force_killed_ready_lease():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)

    assert effective_rdcode_manifest_status({
        "status": "ready",
        "leaseExpiresAt": (now + timedelta(seconds=5)).isoformat(),
    }, now=now) == "ready"
    assert effective_rdcode_manifest_status({
        "status": "ready",
        "leaseExpiresAt": (now - timedelta(seconds=1)).isoformat(),
    }, now=now) == "stale"
    assert effective_rdcode_manifest_status({"status": "ready"}, now=now) == "stale"
    assert effective_rdcode_manifest_status({
        "status": "degraded",
        "leaseExpiresAt": (now + timedelta(seconds=5)).isoformat(),
    }, now=now) == "degraded"
    assert effective_rdcode_manifest_status({
        "status": "degraded",
        "leaseExpiresAt": (now - timedelta(seconds=1)).isoformat(),
    }, now=now) == "stale"
    assert effective_rdcode_manifest_status({
        "status": "building",
        "leaseExpiresAt": (now + timedelta(seconds=5)).isoformat(),
    }, now=now) == "building"
    assert effective_rdcode_manifest_status({"status": "building"}, now=now) == "stale"
    assert effective_rdcode_manifest_status({
        "status": "stopping",
        "leaseExpiresAt": (now + timedelta(seconds=5)).isoformat(),
    }, now=now) == "stopping"
    assert effective_rdcode_manifest_status({"status": "stopping"}, now=now) == "stale"


class TestR2CEarlyExitCancellation:
    """Structural regression: early-exit readiness cancellation in generated runner."""

    @staticmethod
    def _runner_source() -> str:
        return render_rdcode_instance_runner_source()

    def test_delay_accepts_optional_abort_signal(self):
        source = self._runner_source()
        assert "function delay(milliseconds, signal = undefined)" in source
        assert "signal?.aborted" in source
        assert 'signal.addEventListener("abort"' in source
        assert "clearTimeout(timer)" in source

    def test_wait_until_accepts_optional_abort_signal(self):
        source = self._runner_source()
        assert "function waitUntil(check, timeoutMs, label, signal = undefined)" in source
        assert re.search(r"if\s*\(\s*signal\?\.aborted\s*\)\s*return", source)
        assert "await delay(250, signal)" in source

    def test_start_desktop_uses_abort_controller(self):
        source = self._runner_source()
        assert "const readinessController = new AbortController()" in source
        assert "readinessController.signal" in source
        assert "readinessController.abort()" in source

    def test_start_desktop_cancels_readiness_on_early_exit(self):
        source = self._runner_source()
        assert "catch (error)" in source
        assert re.search(
            r"catch\s*\(\s*error\s*\)\s*\{[^}]*readinessController\.abort\(\s*\)[^}]*throw\s+error",
            source,
        )

    def test_start_desktop_drains_readiness_after_success(self):
        source = self._runner_source()
        assert "readinessController.abort();" in source
        refs = [m.start() for m in re.finditer(r"readinessController\.abort\(\)", source)]
        assert len(refs) >= 2, "must have abort in both catch and after-race success path"

    def test_wait_until_preserves_signal_reason_check(self):
        source = self._runner_source()
        assert 'fail("INTERRUPTED", `received ${signalReason}' in source

    def test_delay_returns_immediately_when_already_aborted(self):
        source = self._runner_source()
        assert "if (signal?.aborted) return resolve()" in source

    def test_runner_source_is_syntactically_valid_javascript(self, tmp_path):
        source = self._runner_source()
        runner_path = tmp_path / "runner.mjs"
        runner_path.write_text(source, encoding="utf-8")
        import subprocess
        result = subprocess.run(
            ["node", "--check", str(runner_path)],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, f"node --check failed: {result.stderr}"


class TestR2CPostLockSourceDrift:
    """Structural regression: post-lock source-fingerprint recomputation."""

    @staticmethod
    def _runner_source() -> str:
        return render_rdcode_instance_runner_source()

    def test_source_fingerprint_is_recomputed_after_lock_before_build(self):
        source = self._runner_source()
        lock_index = source.index("lock = acquireCheckoutLock(spec);")
        fingerprint_index = source.index("computeSourceFingerprint(root);")
        build_index = source.index("await ensureBuild(spec);")
        assert lock_index < fingerprint_index < build_index, (
            "computeSourceFingerprint must appear after acquireCheckoutLock "
            "and before ensureBuild in the generated runner source"
        )

    def test_source_drift_fails_on_mismatch(self):
        source = self._runner_source()
        assert 'fail("SOURCE_DRIFT"' in source
        assert "recomputedSourceFingerprint !== spec.build.sourceFingerprint" in source
        assert "checkout source changed between instance spec and lock acquisition" in source

    def test_runner_source_includes_all_build_inputs_and_ignored_parts(self):
        source = self._runner_source()
        for entry in (
            "package.json",
            "pnpm-lock.yaml",
            "pnpm-workspace.yaml",
            "tsconfig.base.json",
            "vite.config.ts",
            "apps/desktop",
            "apps/server",
            "apps/web",
            "packages",
            "scripts",
        ):
            assert entry in source, f"build input {entry!r} missing from runner source"
        for part in ("node_modules", "dist", "dist-electron", ".vite-plus", "tmp"):
            assert part in source, f"ignored part {part!r} missing from runner source"

    def test_runner_source_fingerprint_hash_parity(self, tmp_path):
        """Prove Node runner fingerprint equals Python compute_rdcode_source_fingerprint."""
        import subprocess

        t3_root = tmp_path / "t3code"
        t3_root.mkdir()
        for d in ("apps/desktop", "apps/server", "apps/web", "packages", "scripts"):
            (t3_root / d).mkdir(parents=True)
        (t3_root / "package.json").write_text('{"name":"parity-test","private":true}\n', encoding="utf-8")
        (t3_root / "pnpm-lock.yaml").write_text("lockfileVersion: 9.0\n", encoding="utf-8")
        (t3_root / "pnpm-workspace.yaml").write_text("packages:\n  - packages/*\n", encoding="utf-8")
        (t3_root / "tsconfig.base.json").write_text('{"compilerOptions":{"strict":true}}\n', encoding="utf-8")
        (t3_root / "vite.config.ts").write_text("import { defineConfig } from 'vite';\nexport default defineConfig({});\n", encoding="utf-8")
        (t3_root / "apps" / "web" / "index.html").write_text("<!DOCTYPE html>\n<html></html>\n", encoding="utf-8")
        (t3_root / "apps" / "server" / "main.ts").write_text("console.log('server');\n", encoding="utf-8")
        (t3_root / "apps" / "desktop" / "electron.ts").write_text("// electron main\n", encoding="utf-8")
        (t3_root / "packages" / "shared").mkdir(parents=True, exist_ok=True)
        (t3_root / "packages" / "shared" / "index.ts").write_text("export const version = 1;\n", encoding="utf-8")
        (t3_root / "scripts" / "build.mjs").write_text("import './bundle.js';\n", encoding="utf-8")
        (t3_root / "scripts" / "build.mjs").write_text("import './bundle.js';\n", encoding="utf-8")

        subprocess.run(["git", "init", "-b", "main"], cwd=str(t3_root), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "parity@test.local"], cwd=str(t3_root), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Parity Test"], cwd=str(t3_root), capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=str(t3_root), capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial parity probe"], cwd=str(t3_root), capture_output=True)

        python_fp = rdcode_instance.compute_rdcode_source_fingerprint(t3_root)
        assert len(python_fp) == 64 and all(c in "0123456789abcdef" for c in python_fp)

        source = self._runner_source()
        execution_marker = "\nlet exitCode = 1;\n"
        execution_start = source.find(execution_marker)
        assert execution_start >= 0, "runner source structure changed: cannot find execution block start"

        test_source = (
            source[:execution_start]
            + "\nconst testRoot = process.argv[2];\n"
            + "if (testRoot) {\n"
            + "  process.stdout.write(computeSourceFingerprint(testRoot));\n"
            + "  process.exit(0);\n"
            + "}\n"
            + source[execution_start:]
        )

        runner_path = tmp_path / "fingerprint_parity.mjs"
        runner_path.write_text(test_source, encoding="utf-8")

        result = subprocess.run(
            ["node", str(runner_path), str(t3_root)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"node fingerprint parity probe failed: {result.stderr}"
        node_fp = result.stdout.strip()
        assert node_fp == python_fp, (
            f"fingerprint mismatch:\n  node   = {node_fp}\n  python = {python_fp}"
        )


class TestR2CCorruptLockSafeguards:
    """Structural regression: corrupted checkout-lock behaviour."""

    @staticmethod
    def _runner_source() -> str:
        return render_rdcode_instance_runner_source()

    def test_corrupt_lock_fails_closed_with_explicit_reason(self):
        source = self._runner_source()
        assert 'fail("CHECKOUT_LOCKED", `unreadable lock requires review:' in source, (
            "runner must fail closed when lock file is unreadable (corrupt JSON)"
        )
        assert 'fail("CHECKOUT_LOCKED", `invalid lock requires review:' in source, (
            "runner must fail closed when lock structure is invalid "
            "(wrong version, missing ownerToken, etc.)"
        )
        lock_fn = source.index("function acquireCheckoutLock(spec)")
        release_fn = source.index("function releaseCheckoutLock()")
        assert lock_fn < release_fn, (
            "acquireCheckoutLock must be defined before releaseCheckoutLock"
        )

    def test_never_uses_path_based_kill(self):
        source = self._runner_source()
        assert "__dirname" not in source
        assert "force_kill" not in source

    def test_normal_failure_releases_only_own_lock_in_finally(self):
        source = self._runner_source()
        finally_marker = "} finally {"
        assert finally_marker in source
        finally_block = source[source.index(finally_marker):]
        assert "releaseCheckoutLock();" in finally_block, (
            "releaseCheckoutLock must be called from the finally block"
        )
        release_fn = source[source.index("function releaseCheckoutLock() {"):]
        assert "if (!lock) return;" in release_fn, (
            "releaseCheckoutLock must be a no-op when lock was never acquired"
        )
        assert "current.ownerToken === lock.ownerToken" in release_fn, (
            "releaseCheckoutLock must verify ownership before unlinking"
        )
        assert "NodeFS.unlinkSync(lock.path);" in release_fn, (
            "releaseCheckoutLock must unlink only when ownerToken matches"
        )
