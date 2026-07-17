"""Generated Node runner for one deterministic RD-Code desktop instance."""
from __future__ import annotations


def render_rdcode_instance_runner_source() -> str:
    """Return the build-once, manifest-driven production desktop runner."""
    return r'''#!/usr/bin/env node
import * as NodeChildProcess from "node:child_process";
import * as NodeCrypto from "node:crypto";
import * as NodeFS from "node:fs";
import * as NodeNet from "node:net";
import * as NodePath from "node:path";
import NodeProcess from "node:process";
import * as NodeURL from "node:url";

const root = NodePath.dirname(NodeURL.fileURLToPath(import.meta.url));
const isWindows = NodeProcess.platform === "win32";
const validateOnly = NodeProcess.argv.includes("--validate-only");
let activeChild = null;
let activeExit = null;
let signalReason = null;
let manifest = null;
let lock = null;
let heartbeatTimer = null;
let heartbeatBusy = false;
let healthFailureReason = null;

function argumentValue(name) {
  const index = NodeProcess.argv.indexOf(name);
  return index >= 0 ? NodeProcess.argv[index + 1] : undefined;
}

function fail(code, message) {
  throw new Error(`${code}: ${message}`);
}

function readJson(path) {
  return JSON.parse(NodeFS.readFileSync(path, "utf8"));
}

function samePath(left, right) {
  const normalizedLeft = NodePath.resolve(left);
  const normalizedRight = NodePath.resolve(right);
  return isWindows
    ? normalizedLeft.toLowerCase() === normalizedRight.toLowerCase()
    : normalizedLeft === normalizedRight;
}

function existingRealPath(path) {
  try {
    return NodeFS.realpathSync(path);
  } catch {
    return null;
  }
}

function discoverOnPath(command) {
  const pathKey = Object.keys(NodeProcess.env).find((key) => key.toLowerCase() === "path");
  const pathValue = pathKey ? NodeProcess.env[pathKey] ?? "" : "";
  const pathExtKey = Object.keys(NodeProcess.env).find((key) => key.toLowerCase() === "pathext");
  const extensions = isWindows
    ? (pathExtKey ? NodeProcess.env[pathExtKey] ?? "" : ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean)
    : [""];
  for (const directory of pathValue.split(NodePath.delimiter)) {
    const normalizedDirectory = directory.trim().replace(/^"|"$/g, "");
    if (!normalizedDirectory) continue;
    for (const extension of extensions) {
      const candidate = existingRealPath(NodePath.join(normalizedDirectory, `${command}${extension}`));
      if (candidate) return candidate;
    }
  }
  return null;
}

function discoverPwsh() {
  const installed = discoverOnPath("pwsh");
  if (installed) return installed;
  let parent = root;
  while (true) {
    for (const relative of [
      NodePath.join("powershell-portable", "PowerShell", "7", "pwsh.exe"),
      NodePath.join(".devframe-runtime", "powershell-portable", "PowerShell", "7", "pwsh.exe"),
    ]) {
      const candidate = existingRealPath(NodePath.join(parent, relative));
      if (candidate) return candidate;
    }
    const next = NodePath.dirname(parent);
    if (samePath(next, parent)) break;
    parent = next;
  }
  return null;
}

function requireExactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail("INVALID_SPEC", `${label} must be an object`);
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    fail("INVALID_SPEC", `${label} fields do not match the version 1 contract`);
  }
}

function canonicalJson(value) {
  if (value === null || typeof value === "boolean" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    return JSON.stringify(value).replace(/[\u007f-\uffff]/g, (character) =>
      `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${canonicalJson(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

function validateSpec(spec, inputSpecPath) {
  requireExactKeys(spec, [
    "version", "instanceId", "controlPlane", "ports", "paths", "rendererEnvironment",
    "desktopEnvironment", "build", "concurrency", "tools", "launch",
  ], "spec");
  if (spec?.version !== 1) fail("INVALID_SPEC", "version must equal 1");
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(spec.instanceId ?? "")) {
    fail("INVALID_SPEC", "instanceId is unsafe");
  }
  requireExactKeys(spec.controlPlane, ["host", "port", "baseUrl", "clientPlanUrl", "clientManifestUrl"], "controlPlane");
  requireExactKeys(spec.ports, ["controlPlane", "t3Backend", "cdp"], "ports");
  requireExactKeys(spec.paths, [
    "t3Root", "runtimeRoot", "instanceDir", "appDataDir", "localAppDataDir", "t3Home", "specPath",
    "manifestPath", "buildStampPath", "checkoutLockPath",
  ], "paths");
  requireExactKeys(spec.build, ["sourceFingerprint", "fingerprint", "toolchain"], "build");
  requireExactKeys(
    spec.build.toolchain,
    ["node", "nodePath", "pnpm", "pnpmPath", "command"],
    "build.toolchain",
  );
  requireExactKeys(spec.concurrency, ["mode", "lockPath"], "concurrency");
  requireExactKeys(spec.tools, ["nodePath", "pnpmPath", "pwshPath"], "tools");
  requireExactKeys(spec.launch, ["readinessTimeoutSeconds", "exitAfterReadySeconds", "forceBuild"], "launch");

  if (!samePath(spec.paths?.t3Root ?? "", root)) {
    fail("INVALID_SPEC", "paths.t3Root does not match the runner checkout");
  }
  for (const key of [
    "runtimeRoot", "instanceDir", "appDataDir", "localAppDataDir", "t3Home", "specPath", "manifestPath",
    "buildStampPath", "checkoutLockPath",
  ]) {
    if (!NodePath.isAbsolute(spec.paths?.[key] ?? "")) fail("INVALID_SPEC", `paths.${key} must be absolute`);
  }
  const expectedInstanceDir = NodePath.join(spec.paths.runtimeRoot, "rd-code", "instances", spec.instanceId);
  if (!samePath(spec.paths.instanceDir, expectedInstanceDir)) {
    fail("INVALID_SPEC", "paths.instanceDir is not canonical for runtimeRoot and instanceId");
  }
  const expectedInstancePaths = {
    appDataDir: NodePath.join(spec.paths.instanceDir, "appdata"),
    localAppDataDir: NodePath.join(spec.paths.instanceDir, "local-appdata"),
    t3Home: NodePath.join(spec.paths.instanceDir, "t3-home"),
    specPath: NodePath.join(spec.paths.instanceDir, "instance-spec.json"),
    manifestPath: NodePath.join(spec.paths.instanceDir, "instance-manifest.json"),
  };
  for (const [key, expected] of Object.entries(expectedInstancePaths)) {
    if (!samePath(spec.paths[key], expected)) fail("INVALID_SPEC", `paths.${key} is not canonical`);
  }
  if (!samePath(spec.paths.specPath, inputSpecPath)) {
    fail("INVALID_SPEC", "paths.specPath does not match --instance-spec");
  }
  const checkoutStateDir = NodePath.join(root, "apps", "desktop", ".electron-runtime", "devframe-rdcode");
  const expectedBuildStamp = NodePath.join(checkoutStateDir, "build-stamp.json");
  const expectedCheckoutLock = NodePath.join(checkoutStateDir, "checkout.lock");
  if (!samePath(spec.paths.buildStampPath, expectedBuildStamp)) {
    fail("INVALID_SPEC", "paths.buildStampPath is not the canonical checkout build stamp");
  }
  if (!samePath(spec.paths.checkoutLockPath, expectedCheckoutLock)) {
    fail("INVALID_SPEC", "paths.checkoutLockPath is not the canonical checkout lock");
  }
  if (!samePath(spec.concurrency?.lockPath ?? "", expectedCheckoutLock)) {
    fail("INVALID_SPEC", "concurrency.lockPath disagrees with the canonical checkout lock");
  }
  const ports = [spec.ports?.controlPlane, spec.ports?.t3Backend, spec.ports?.cdp];
  if (ports.some((port) => !Number.isInteger(port) || port < 1 || port > 65_535)) {
    fail("INVALID_SPEC", "ports must be integers between 1 and 65535");
  }
  if (new Set(ports).size !== ports.length) fail("INVALID_SPEC", "ports must be distinct");
  const host = String(spec.controlPlane.host ?? "").toLowerCase();
  const loopbackHost =
    host === "localhost" ||
    (NodeNet.isIP(host) === 4 && host.startsWith("127."));
  if (!loopbackHost) {
    fail("INVALID_SPEC", "control plane must be localhost or IPv4 loopback");
  }
  if (spec.controlPlane.port !== spec.ports.controlPlane) {
    fail("INVALID_SPEC", "controlPlane.port disagrees with ports.controlPlane");
  }
  const renderedHost = host.includes(":") ? `[${host}]` : host;
  const expectedBaseUrl = `http://${renderedHost}:${spec.ports.controlPlane}`;
  if (spec.controlPlane.baseUrl !== expectedBaseUrl) {
    fail("INVALID_SPEC", "controlPlane.baseUrl disagrees with host and port");
  }
  if (spec.controlPlane.clientPlanUrl !== `${spec.controlPlane.baseUrl}/client-plan.json`) {
    fail("INVALID_SPEC", "clientPlanUrl disagrees with baseUrl");
  }
  if (spec.controlPlane.clientManifestUrl !== `${spec.controlPlane.baseUrl}/client-manifest.json`) {
    fail("INVALID_SPEC", "clientManifestUrl disagrees with baseUrl");
  }
  requireExactKeys(spec.desktopEnvironment, [
    "APPDATA", "LOCALAPPDATA", "T3CODE_HOME", "T3CODE_PORT",
    "T3CODE_DESKTOP_APP_USER_MODEL_ID", "T3CODE_DISABLE_AUTO_UPDATE",
  ], "desktopEnvironment");
  const expectedDesktopEnvironment = {
    APPDATA: spec.paths.appDataDir,
    LOCALAPPDATA: spec.paths.localAppDataDir,
    T3CODE_HOME: spec.paths.t3Home,
    T3CODE_PORT: String(spec.ports.t3Backend),
    T3CODE_DESKTOP_APP_USER_MODEL_ID: `com.rdcode.client.${spec.instanceId.toLowerCase()}`,
    T3CODE_DISABLE_AUTO_UPDATE: "1",
  };
  for (const [key, expected] of Object.entries(expectedDesktopEnvironment)) {
    const matches = key === "APPDATA" || key === "LOCALAPPDATA" || key === "T3CODE_HOME"
      ? samePath(spec.desktopEnvironment[key] ?? "", expected)
      : spec.desktopEnvironment[key] === expected;
    if (!matches) fail("INVALID_SPEC", `desktopEnvironment.${key} disagrees with the instance contract`);
  }
  if (!spec.rendererEnvironment || typeof spec.rendererEnvironment !== "object" || Array.isArray(spec.rendererEnvironment)) {
    fail("INVALID_SPEC", "rendererEnvironment must be an object");
  }
  for (const [key, value] of Object.entries(spec.rendererEnvironment)) {
    if (!/^VITE_DEVFRAME_[A-Z0-9_]+$/.test(key) || typeof value !== "string") {
      fail("INVALID_SPEC", `rendererEnvironment.${key} is not an allowed string setting`);
    }
  }
  if (spec.rendererEnvironment?.VITE_DEVFRAME_CLIENT_PLAN_URL !== spec.controlPlane.clientPlanUrl) {
    fail("INVALID_SPEC", "renderer client-plan URL disagrees with the control plane");
  }
  if (spec.rendererEnvironment?.VITE_DEVFRAME_CLIENT_MANIFEST_URL !== spec.controlPlane.clientManifestUrl) {
    fail("INVALID_SPEC", "renderer client-manifest URL disagrees with the control plane");
  }
  if (typeof spec.rendererEnvironment?.VITE_DEVFRAME_REALTIME_MODE !== "string" ||
      !spec.rendererEnvironment.VITE_DEVFRAME_REALTIME_MODE) {
    fail("INVALID_SPEC", "renderer realtime mode is required");
  }
  if (spec.concurrency?.mode !== "exclusive-checkout") {
    fail("INVALID_SPEC", "the first production contract requires exclusive-checkout mode");
  }
  if (!/^[a-f0-9]{64}$/.test(spec.build.sourceFingerprint ?? "") || !/^[a-f0-9]{64}$/.test(spec.build.fingerprint ?? "")) {
    fail("INVALID_SPEC", "build fingerprints must be lowercase SHA-256 values");
  }
  const expectedBuildFingerprint = NodeCrypto.createHash("sha256").update(canonicalJson({
    sourceFingerprint: spec.build.sourceFingerprint,
    rendererEnvironment: spec.rendererEnvironment,
    toolchain: spec.build.toolchain,
  })).digest("hex");
  if (spec.build.fingerprint !== expectedBuildFingerprint) {
    fail("INVALID_SPEC", "build.fingerprint disagrees with renderer, source, or toolchain inputs");
  }
  if (spec.build.toolchain.command !== "pnpm build:desktop") {
    fail("INVALID_SPEC", "build.toolchain.command is unsupported");
  }
  if (typeof spec.build.toolchain.node !== "string" || !spec.build.toolchain.node ||
      typeof spec.build.toolchain.pnpm !== "string" || !spec.build.toolchain.pnpm) {
    fail("INVALID_SPEC", "build toolchain versions must be non-empty strings");
  }
  if (!Number.isInteger(spec.launch.readinessTimeoutSeconds) ||
      spec.launch.readinessTimeoutSeconds < 1 || spec.launch.readinessTimeoutSeconds > 600) {
    fail("INVALID_SPEC", "launch.readinessTimeoutSeconds is out of range");
  }
  if (!Number.isInteger(spec.launch.exitAfterReadySeconds) ||
      spec.launch.exitAfterReadySeconds < 0 || spec.launch.exitAfterReadySeconds > 600) {
    fail("INVALID_SPEC", "launch.exitAfterReadySeconds is out of range");
  }
  if (typeof spec.launch.forceBuild !== "boolean") {
    fail("INVALID_SPEC", "launch.forceBuild must be a boolean");
  }
  const runningNode = existingRealPath(NodeProcess.execPath);
  const discoveredPnpm = discoverOnPath("pnpm");
  if (!runningNode || !samePath(spec.tools.nodePath ?? "", runningNode)) {
    fail("INVALID_SPEC", "tools.nodePath does not match the running Node executable");
  }
  if (!discoveredPnpm || !samePath(spec.tools.pnpmPath ?? "", discoveredPnpm)) {
    fail("INVALID_SPEC", "tools.pnpmPath does not match the original PATH resolution");
  }
  if (!samePath(spec.build.toolchain.nodePath ?? "", spec.tools.nodePath) ||
      !samePath(spec.build.toolchain.pnpmPath ?? "", spec.tools.pnpmPath)) {
    fail("INVALID_SPEC", "build toolchain paths disagree with the pinned tools");
  }
  const discoveredPwsh = discoverPwsh();
  if (spec.tools?.pwshPath === null) {
    if (discoveredPwsh !== null) fail("INVALID_SPEC", "tools.pwshPath omits the discovered pwsh executable");
  } else if (!NodePath.isAbsolute(spec.tools?.pwshPath ?? "") ||
      !discoveredPwsh || !samePath(spec.tools.pwshPath, discoveredPwsh)) {
    fail("INVALID_SPEC", "tools.pwshPath does not match the deterministic discovery result");
  }
  return spec;
}

function validatePinnedToolVersions(spec) {
  const actualNodeVersion = NodeProcess.version;
  const actualPnpmVersion = pinnedCommandVersion(spec.tools.pnpmPath);
  if (spec.build.toolchain.node !== actualNodeVersion) {
    fail("INVALID_SPEC", "build.toolchain.node does not match the running pinned Node version");
  }
  if (!actualPnpmVersion || spec.build.toolchain.pnpm !== actualPnpmVersion) {
    fail("INVALID_SPEC", "build.toolchain.pnpm does not match the pinned pnpm version in the T3 root");
  }
}

function atomicWriteJson(path, value) {
  NodeFS.mkdirSync(NodePath.dirname(path), { recursive: true });
  const temporaryPath = `${path}.${NodeProcess.pid}.${NodeCrypto.randomUUID()}.tmp`;
  NodeFS.writeFileSync(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  NodeFS.renameSync(temporaryPath, path);
}

function nowIso() {
  return new Date().toISOString();
}

function writeManifest(status, details = {}) {
  manifest = {
    ...manifest,
    status,
    updatedAt: nowIso(),
    ...details,
  };
  atomicWriteJson(manifest.spec.paths.manifestPath, manifest);
}

function readyLease() {
  const healthyAt = Date.now();
  return {
    heartbeatAt: new Date(healthyAt).toISOString(),
    leaseExpiresAt: new Date(healthyAt + 5_000).toISOString(),
  };
}

function stopHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

function startSupervisorLease() {
  stopHeartbeat();
  const renew = () => {
    if (!heartbeatTimer || !manifest) return;
    const lease = readyLease();
    writeManifest(manifest.status, {
      supervisorHeartbeatAt: lease.heartbeatAt,
      leaseExpiresAt: lease.leaseExpiresAt,
    });
  };
  heartbeatTimer = setInterval(renew, 1_000);
  renew();
}

function startHeartbeat(spec, rendererTarget) {
  stopHeartbeat();
  let lastHealthyAt = Date.now();
  let consecutiveHealthFailures = 0;
  const stopForHealthFailure = async (message) => {
    stopHeartbeat();
    healthFailureReason = message;
    let cleanupError = null;
    try {
      await stopActiveChild("health-lost");
    } catch (error) {
      cleanupError = error;
    }
    if (cleanupError) healthFailureReason = `${message}; ${cleanupError.message}`;
    writeManifest(cleanupError ? "cleanup-failed" : "failed", {
      error: healthFailureReason,
      leaseExpiresAt: null,
    });
  };
  const recordHealthFailure = async (message) => {
    consecutiveHealthFailures += 1;
    const leaseExpiresAt = lastHealthyAt + 5_000;
    if (Date.now() <= leaseExpiresAt) {
      writeManifest("degraded", {
        healthProbeFailure: message,
        consecutiveHealthFailures,
        heartbeatAt: new Date(lastHealthyAt).toISOString(),
        leaseExpiresAt: new Date(leaseExpiresAt).toISOString(),
      });
      return;
    }
    await stopForHealthFailure(message);
  };
  const renew = async () => {
    if (heartbeatBusy || !heartbeatTimer) return;
    heartbeatBusy = true;
    const timer = heartbeatTimer;
    try {
      const [controlPlaneHealthy, backendHealthy, currentRenderer] = await Promise.all([
        httpReady(spec.controlPlane.clientPlanUrl),
        portReady(spec.ports.t3Backend),
        rendererReady(spec, rendererTarget.id),
      ]);
      if (heartbeatTimer !== timer) return;
      if (!controlPlaneHealthy || !backendHealthy || !currentRenderer) {
        await recordHealthFailure("HEALTH_LOST: control plane, backend, or renderer target became unavailable");
        return;
      }
      lastHealthyAt = Date.now();
      consecutiveHealthFailures = 0;
      writeManifest("ready", {
        ...readyLease(),
        healthProbeFailure: null,
        consecutiveHealthFailures: 0,
      });
    } catch (error) {
      if (heartbeatTimer === timer) {
        await recordHealthFailure(`HEALTH_PROBE_FAILED: ${error.message}`);
      }
    } finally {
      heartbeatBusy = false;
    }
  };
  heartbeatTimer = setInterval(() => void renew(), 1_000);
  void renew();
}

function acquireCheckoutLock(spec) {
  const path = spec.concurrency.lockPath;
  NodeFS.mkdirSync(NodePath.dirname(path), { recursive: true });
  const ownerToken = NodeCrypto.randomUUID();
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const handle = NodeFS.openSync(path, "wx", 0o600);
      const value = {
        version: 1,
        instanceId: spec.instanceId,
        ownerToken,
        launcherPid: NodeProcess.pid,
        createdAt: nowIso(),
      };
      NodeFS.writeFileSync(handle, `${JSON.stringify(value, null, 2)}\n`, "utf8");
      NodeFS.closeSync(handle);
      return { path, ownerToken, recoveredLockPath: null };
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;
      let existing;
      try {
        existing = readJson(path);
      } catch {
        fail("CHECKOUT_LOCKED", `unreadable lock requires review: ${path}`);
      }
      if (existing?.version !== 1 ||
          !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(existing.instanceId ?? "") ||
          typeof existing.ownerToken !== "string" || !existing.ownerToken ||
          !Number.isInteger(existing.launcherPid) || existing.launcherPid < 1 ||
          typeof existing.createdAt !== "string" || !existing.createdAt) {
        fail("CHECKOUT_LOCKED", `invalid lock requires review: ${path}`);
      }
      if (processExists(existing.launcherPid)) {
        fail("CHECKOUT_LOCKED", `instance ${existing.instanceId ?? "unknown"} owns launcher PID ${existing.launcherPid}`);
      }
      const archived = `${path}.stale.${Date.now()}.${NodeCrypto.randomUUID()}.json`;
      try {
        NodeFS.renameSync(path, archived);
        return acquireCheckoutLockAfterRecovery(spec, ownerToken, archived);
      } catch (renameError) {
        if (renameError?.code === "ENOENT") continue;
        throw renameError;
      }
    }
  }
  fail("CHECKOUT_LOCKED", `concurrent lock recovery did not settle: ${path}`);
}

function acquireCheckoutLockAfterRecovery(spec, ownerToken, recoveredLockPath) {
  const path = spec.concurrency.lockPath;
  let handle;
  try {
    handle = NodeFS.openSync(path, "wx", 0o600);
  } catch (error) {
    if (error?.code === "EEXIST") fail("CHECKOUT_LOCKED", `another launcher acquired the recovered lock: ${path}`);
    throw error;
  }
  NodeFS.writeFileSync(handle, `${JSON.stringify({
    version: 1,
    instanceId: spec.instanceId,
    ownerToken,
    launcherPid: NodeProcess.pid,
    createdAt: nowIso(),
    recoveredLockPath,
  }, null, 2)}\n`, "utf8");
  NodeFS.closeSync(handle);
  return { path, ownerToken, recoveredLockPath };
}

function processExists(rawPid) {
  const pid = Number(rawPid);
  if (!Number.isInteger(pid) || pid < 1) return false;
  try {
    NodeProcess.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

function releaseCheckoutLock() {
  if (!lock) return;
  try {
    const current = readJson(lock.path);
    if (current.ownerToken === lock.ownerToken) NodeFS.unlinkSync(lock.path);
  } catch (error) {
    if (error?.code !== "ENOENT") console.error(`[rdcode-runner] Failed to release checkout lock: ${error.message}`);
  }
  lock = null;
}

function delay(milliseconds, signal = undefined) {
  return new Promise((resolve) => {
    if (signal?.aborted) return resolve();
    const timer = setTimeout(resolve, milliseconds);
    if (signal) {
      signal.addEventListener("abort", () => {
        clearTimeout(timer);
        resolve();
      }, { once: true });
    }
  });
}

async function httpReady(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1_500) });
    return response.ok;
  } catch {
    return false;
  }
}

async function jsonReady(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1_500) });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

function evaluateRenderer(webSocketDebuggerUrl) {
  return new Promise((resolve) => {
    if (typeof WebSocket !== "function") {
      resolve(false);
      return;
    }
    const socket = new WebSocket(webSocketDebuggerUrl);
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      try {
        socket.close();
      } catch (error) {
        console.error(`[rdcode-runner] renderer probe socket close failed: ${error.message}`);
      }
      resolve(value);
    };
    const timeout = setTimeout(() => finish(false), 1_500);
    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({
        id: 1,
        method: "Runtime.evaluate",
        params: {
          expression: 'Boolean(document.querySelector("#root")?.childElementCount)',
          returnByValue: true,
        },
      }));
    });
    socket.addEventListener("message", (event) => {
      try {
        const message = JSON.parse(String(event.data));
        if (message.id === 1) finish(message.result?.result?.value === true);
      } catch {
        finish(false);
      }
    });
    socket.addEventListener("error", () => finish(false));
    socket.addEventListener("close", () => finish(false));
  });
}

async function rendererReady(spec, expectedTargetId = null) {
  const targets = await jsonReady(`http://127.0.0.1:${spec.ports.cdp}/json/list`);
  if (!Array.isArray(targets)) return null;
  const target = targets.find((candidate) =>
    candidate?.type === "page" &&
    typeof candidate.url === "string" && candidate.url.startsWith("t3code://app/") &&
    typeof candidate.webSocketDebuggerUrl === "string" &&
    (!expectedTargetId || candidate.id === expectedTargetId));
  if (!target || !(await evaluateRenderer(target.webSocketDebuggerUrl))) return null;
  return { id: target.id, type: target.type, title: target.title ?? "", url: target.url };
}

function portReady(port) {
  return new Promise((resolve) => {
    const socket = NodeNet.createConnection({ host: "127.0.0.1", port });
    const done = (value) => {
      socket.destroy();
      resolve(value);
    };
    socket.setTimeout(750);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
  });
}

async function waitUntil(check, timeoutMs, label, signal = undefined) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (signal?.aborted) return;
    if (signalReason) fail("INTERRUPTED", `received ${signalReason} while waiting for ${label}`);
    if (await check()) return;
    await delay(250, signal);
  }
  if (signal?.aborted) return;
  fail("READINESS_TIMEOUT", `${label} was not ready within ${timeoutMs}ms`);
}

async function acceptOwnershipGate(spec) {
  if (validateOnly) return;
  const gate = argumentValue("--ownership-gate");
  if (!gate) fail("INVALID_ARGUMENT", "--ownership-gate <path> is required outside validation mode");
  const resolvedGate = NodePath.resolve(gate);
  if (!samePath(NodePath.dirname(resolvedGate), spec.paths.instanceDir) ||
      !/^\.ownership-gate\.[A-Za-z0-9.-]+\.ready$/.test(NodePath.basename(resolvedGate))) {
    fail("INVALID_ARGUMENT", "ownership gate must be a generated file inside the instance directory");
  }
  await waitUntil(() => NodeFS.existsSync(resolvedGate), 10_000, "Python process ownership gate");
  try {
    NodeFS.unlinkSync(resolvedGate);
  } catch (error) {
    fail("OWNERSHIP_GATE_FAILED", error.message);
  }
}

function spawnCommand(command, args, env) {
  const { executable, spawnArgs } = commandInvocation(command, args);
  const child = NodeChildProcess.spawn(executable, spawnArgs, {
    cwd: root,
    env,
    stdio: "inherit",
    shell: false,
    windowsVerbatimArguments: isWindows,
  });
  activeChild = child;
  activeExit = new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => resolve({ code: code ?? 1, signal }));
  });
  return child;
}

function commandInvocation(command, args) {
  const commandLine = [command, ...args]
    .map((value) => `"${String(value).replaceAll('"', '""')}"`)
    .join(" ");
  return {
    executable: isWindows ? (NodeProcess.env.ComSpec ?? "cmd.exe") : command,
    spawnArgs: isWindows ? ["/d", "/s", "/c", `"${commandLine}"`] : args,
  };
}

function pinnedCommandVersion(command) {
  const { executable, spawnArgs } = commandInvocation(command, ["--version"]);
  const result = NodeChildProcess.spawnSync(executable, spawnArgs, {
    cwd: root,
    env: NodeProcess.env,
    encoding: "utf8",
    shell: false,
    windowsVerbatimArguments: isWindows,
    windowsHide: true,
    timeout: 10_000,
  });
  if (result.error || result.status !== 0) return null;
  const output = String(result.stdout || result.stderr || "").trim().split(/\r?\n/);
  return output[0]?.trim() || null;
}

function sanitizedEnvironment({ desktop = false } = {}) {
  const environment = {};
  for (const [key, value] of Object.entries(NodeProcess.env)) {
    const normalized = key.toUpperCase();
    if (normalized.startsWith("VITE_") ||
        normalized === "DEVFRAME_T3_FORCE_BUILD" ||
        normalized.startsWith("T3CODE_") ||
        normalized === "ELECTRON_RUN_AS_NODE") {
      continue;
    }
    if (desktop && (normalized === "APPDATA" || normalized === "LOCALAPPDATA")) {
      continue;
    }
    environment[key] = value;
  }
  return environment;
}

async function stopActiveChild(reason) {
  stopHeartbeat();
  const child = activeChild;
  if (!child || child.exitCode !== null) return;
  writeManifest("stopping", { ...readyLease(), stopReason: reason });
  startSupervisorLease();
  try {
    if (isWindows) {
      await taskkillTree(child.pid);
    } else {
      child.kill("SIGTERM");
    }
    await Promise.race([activeExit, delay(10_000)]);
    if (child.exitCode === null && !isWindows) child.kill("SIGKILL");
    if (child.exitCode === null) {
      writeManifest("cleanup-failed", {
        error: `CLEANUP_FAILED: owned process tree rooted at PID ${child.pid} is still alive`,
        leaseExpiresAt: null,
      });
      fail("CLEANUP_FAILED", `owned process tree rooted at PID ${child.pid} is still alive`);
    }
  } finally {
    stopHeartbeat();
  }
}

function taskkillTree(pid) {
  return new Promise((resolve) => {
    const killer = NodeChildProcess.spawn("taskkill", ["/PID", String(pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
      shell: false,
    });
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      resolve();
    };
    const timeout = setTimeout(() => {
      killer.kill();
      finish();
    }, 10_000);
    killer.once("error", finish);
    killer.once("exit", finish);
  });
}

function fileDigest(path) {
  const digest = NodeCrypto.createHash("sha256");
  digest.update(NodeFS.readFileSync(path));
  return { path, sha256: digest.digest("hex"), size: NodeFS.statSync(path).size };
}

function filesBelow(directory) {
  if (!NodeFS.existsSync(directory)) return [];
  const files = [];
  const pending = [directory];
  while (pending.length > 0) {
    const current = pending.pop();
    for (const entry of NodeFS.readdirSync(current, { withFileTypes: true })) {
      const path = NodePath.join(current, entry.name);
      if (entry.isDirectory()) pending.push(path);
      else if (entry.isFile()) files.push(path);
    }
  }
  return files.sort((left, right) => left.localeCompare(right));
}

function currentBuildOutputs(spec) {
  const rendererRoot = NodePath.join(root, "apps", "web", "dist");
  const desktopRoot = NodePath.join(root, "apps", "desktop", "dist-electron");
  const renderer = NodePath.join(rendererRoot, "index.html");
  const main = NodePath.join(desktopRoot, "main.cjs");
  if (!NodeFS.existsSync(renderer) || !NodeFS.existsSync(main)) return null;
  return [...filesBelow(rendererRoot), ...filesBelow(desktopRoot)].map(fileDigest);
}

function buildIsCurrent(spec) {
  const outputs = currentBuildOutputs(spec);
  if (!outputs || !NodeFS.existsSync(spec.paths.buildStampPath)) return false;
  try {
    const stamp = readJson(spec.paths.buildStampPath);
    return stamp.fingerprint === spec.build.fingerprint && JSON.stringify(stamp.outputs) === JSON.stringify(outputs);
  } catch {
    return false;
  }
}

const BUILD_INPUTS = [
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
];

const IGNORED_BUILD_PARTS = new Set(["node_modules", "dist", "dist-electron", ".vite-plus", "tmp", ".electron-runtime"]);

function computeSourceFingerprint(t3Root) {
  const digest = NodeCrypto.createHash("sha256");
  if (NodeFS.existsSync(NodePath.join(t3Root, ".git"))) {
    const revision = gitSpawnSyncBuffer(t3Root, ["rev-parse", "HEAD"]);
    const changed = gitSpawnSyncBuffer(t3Root, ["diff", "--name-only", "-z", "HEAD", "--", ...BUILD_INPUTS]);
    const untracked = gitSpawnSyncBuffer(t3Root, ["ls-files", "--others", "--exclude-standard", "-z", "--", ...BUILD_INPUTS]);
    if (revision !== null && changed !== null && untracked !== null) {
      const paths = new Set([...decodeNulPaths(changed), ...decodeNulPaths(untracked)]);
      return hashCheckoutFiles(digest, t3Root, bufferStrip(revision), paths);
    }
  }
  return hashCheckoutFiles(digest, t3Root, Buffer.from("unversioned", "utf8"), fallbackBuildInputs(t3Root));
}

function gitSpawnSyncBuffer(root, args) {
  try {
    const result = NodeChildProcess.spawnSync("git", ["-C", root, ...args], {
      encoding: "buffer",
      windowsHide: true,
      timeout: 30_000,
      stdio: ["ignore", "pipe", "pipe"],
    });
    if (result.status !== 0 || !result.stdout) return null;
    return result.stdout;
  } catch {
    return null;
  }
}

function bufferStrip(buffer) {
  let start = 0;
  let end = buffer.length;
  while (start < end && (buffer[start] === 0x20 || buffer[start] === 0x09 || buffer[start] === 0x0a || buffer[start] === 0x0d)) start++;
  while (end > start && (buffer[end - 1] === 0x20 || buffer[end - 1] === 0x09 || buffer[end - 1] === 0x0a || buffer[end - 1] === 0x0d)) end--;
  return buffer.slice(start, end);
}

function decodeNulPaths(buffer) {
  const paths = new Set();
  const str = buffer.toString("utf8");
  let segment = "";
  for (let i = 0; i < str.length; i++) {
    if (str[i] === "\0") {
      if (segment) paths.add(segment);
      segment = "";
    } else {
      segment += str[i];
    }
  }
  if (segment) paths.add(segment);
  return paths;
}

function hashCheckoutFiles(digest, root, revision, relativePaths) {
  digest.update(revision);
  const unique = [...new Set(relativePaths)].sort();
  for (const relative of unique) {
    const normalized = relative.replace(/\\/g, "/");
    digest.update("\0path\0" + normalized, "utf8");
    const path = NodePath.join(root, normalized);
    try {
      const content = NodeFS.readFileSync(path);
      digest.update(content);
    } catch {
      digest.update("\0deleted", "utf8");
    }
  }
  return digest.digest("hex");
}

function fallbackBuildInputs(root) {
  const paths = new Set();
  for (const relative of BUILD_INPUTS) {
    const candidate = NodePath.join(root, relative);
    try {
      const stat = NodeFS.statSync(candidate);
      if (stat.isFile()) {
        paths.add(relative);
        continue;
      }
      if (!stat.isDirectory()) continue;
      collectFilesBelow(candidate, root, paths);
    } catch {
      continue;
    }
  }
  return paths;
}

function collectFilesBelow(directory, root, paths) {
  const pending = [directory];
  while (pending.length > 0) {
    const current = pending.pop();
    let entries;
    try {
      entries = NodeFS.readdirSync(current, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const fullPath = NodePath.join(current, entry.name);
      if (entry.isDirectory()) {
        pending.push(fullPath);
      } else if (entry.isFile()) {
        const relativePath = NodePath.relative(root, fullPath);
        const parts = relativePath.split(NodePath.sep);
        if (!parts.some((part) => IGNORED_BUILD_PARTS.has(part))) {
          paths.add(parts.join("/"));
        }
      }
    }
  }
}

async function ensureBuild(spec) {
  if (!spec.launch.forceBuild && buildIsCurrent(spec)) {
    writeManifest("build-reused", { buildReused: true });
    return;
  }
  writeManifest("building", { buildReused: false });
  const buildEnv = { ...sanitizedEnvironment(), ...spec.rendererEnvironment };
  const child = spawnCommand(spec.tools.pnpmPath, ["build:desktop"], buildEnv);
  const result = await activeExit;
  activeChild = null;
  if (result.code !== 0) fail("BUILD_FAILED", `pnpm build:desktop exited ${result.code}`);
  const outputs = currentBuildOutputs(spec);
  if (!outputs) fail("BUILD_FAILED", "expected renderer and desktop outputs are missing");
  atomicWriteJson(spec.paths.buildStampPath, {
    version: 1,
    fingerprint: spec.build.fingerprint,
    sourceFingerprint: spec.build.sourceFingerprint,
    toolchain: spec.build.toolchain,
    outputs,
    builtAt: nowIso(),
  });
}

function windowsProcessTree(rootPid) {
  if (!isWindows) return [{ pid: rootPid, parentPid: NodeProcess.pid, role: "runtime-root" }];
  const script = [
    "$all=Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name;",
    `$pending=@(${rootPid}); $seen=@{}; $out=@();`,
    "while($pending.Count -gt 0){$parent=[int]$pending[0];$pending=@($pending | Select-Object -Skip 1);",
    "$children=@($all | Where-Object {$_.ParentProcessId -eq $parent});",
    "foreach($child in $children){if(-not $seen.ContainsKey($child.ProcessId)){$seen[$child.ProcessId]=$true;",
    "$out+=[pscustomobject]@{pid=[int]$child.ProcessId;parentPid=[int]$child.ParentProcessId;role=[string]$child.Name};",
    "$pending+=[int]$child.ProcessId}}}; $out | ConvertTo-Json -Compress",
  ].join(" ");
  const result = NodeChildProcess.spawnSync("powershell.exe", ["-NoProfile", "-Command", script], {
    encoding: "utf8",
    windowsHide: true,
    timeout: 10_000,
  });
  if (result.status !== 0 || !result.stdout.trim()) return [{ pid: rootPid, parentPid: NodeProcess.pid, role: "runtime-root" }];
  const parsed = JSON.parse(result.stdout);
  return [
    { pid: rootPid, parentPid: NodeProcess.pid, role: "runtime-root" },
    ...(Array.isArray(parsed) ? parsed : [parsed]),
  ];
}

async function assertDesktopPortsFree(spec) {
  if (await portReady(spec.ports.t3Backend)) fail("PORT_IN_USE", `T3 backend port ${spec.ports.t3Backend}`);
  if (await portReady(spec.ports.cdp)) fail("PORT_IN_USE", `CDP port ${spec.ports.cdp}`);
}

async function startDesktop(spec) {
  await assertDesktopPortsFree(spec);
  const runtimeEnv = {
    ...sanitizedEnvironment({ desktop: true }),
    ...spec.desktopEnvironment,
    T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT: String(spec.ports.cdp),
  };
  if (spec.tools.pwshPath) {
    const pathKey = Object.keys(runtimeEnv).find((key) => key.toLowerCase() === "path");
    const currentPath = pathKey ? runtimeEnv[pathKey] ?? "" : "";
    if (pathKey && pathKey !== "PATH") delete runtimeEnv[pathKey];
    runtimeEnv.PATH = `${currentPath}${NodePath.delimiter}${NodePath.dirname(spec.tools.pwshPath)}`;
  }
  delete runtimeEnv.ELECTRON_RUN_AS_NODE;
  const child = spawnCommand(spec.tools.pnpmPath, ["start:desktop"], runtimeEnv);
  writeManifest("starting", {
    processes: [{ pid: child.pid, parentPid: NodeProcess.pid, role: "runtime-root" }],
  });
  const timeoutMs = spec.launch.readinessTimeoutSeconds * 1_000;
  const readinessController = new AbortController();
  let rendererTarget = null;
  const readiness = Promise.all([
    waitUntil(() => portReady(spec.ports.t3Backend), timeoutMs, "T3 backend", readinessController.signal),
    waitUntil(async () => {
      rendererTarget = await rendererReady(spec);
      return rendererTarget;
    }, timeoutMs, "mounted RD-Code renderer target", readinessController.signal),
  ]);
  const earlyExit = activeExit.then((result) => fail("EARLY_EXIT", `desktop exited ${result.code} before ready`));
  try {
    await Promise.race([readiness, earlyExit]);
  } catch (error) {
    readinessController.abort();
    throw error;
  }
  readinessController.abort();
  await delay(5_000);
  const stableRenderer = rendererTarget ? await rendererReady(spec, rendererTarget.id) : null;
  if (!(await httpReady(spec.controlPlane.clientPlanUrl)) ||
      !(await portReady(spec.ports.t3Backend)) || !stableRenderer) {
    fail("UNSTABLE_READINESS", "desktop readiness did not remain stable");
  }
  writeManifest("ready", {
    ...readyLease(),
    readyAt: nowIso(),
    processes: windowsProcessTree(child.pid),
    rendererTarget: stableRenderer,
  });
  startHeartbeat(spec, stableRenderer);
  if (spec.launch.exitAfterReadySeconds > 0) {
    await delay(spec.launch.exitAfterReadySeconds * 1_000);
    await stopActiveChild("exit-after-ready");
  }
  return activeExit;
}

async function main() {
  const specPath = argumentValue("--instance-spec");
  if (!specPath) fail("INVALID_ARGUMENT", "--instance-spec <path> is required");
  const resolvedSpecPath = NodePath.resolve(specPath);
  const spec = validateSpec(readJson(resolvedSpecPath), resolvedSpecPath);
  await acceptOwnershipGate(spec);
  lock = acquireCheckoutLock(spec);
  validatePinnedToolVersions(spec);
  const generation = NodeCrypto.randomUUID();
  manifest = {
    version: 1,
    generation,
    instanceId: spec.instanceId,
    specPath: resolvedSpecPath,
    buildFingerprint: spec.build.fingerprint,
    launcherPid: NodeProcess.pid,
    startedAt: nowIso(),
    spec,
  };
  writeManifest(validateOnly ? "validated" : "planned", {
    ownerToken: lock.ownerToken,
    recoveredLockPath: lock.recoveredLockPath,
  });
  if (validateOnly) return 0;
  const recomputedSourceFingerprint = computeSourceFingerprint(root);
  if (recomputedSourceFingerprint !== spec.build.sourceFingerprint) {
    fail("SOURCE_DRIFT", "checkout source changed between instance spec and lock acquisition");
  }
  startSupervisorLease();
  await waitUntil(() => httpReady(spec.controlPlane.clientPlanUrl), 15_000, "DevFrame control plane");
  await assertDesktopPortsFree(spec);
  await ensureBuild(spec);
  const result = await startDesktop(spec);
  stopHeartbeat();
  activeChild = null;
  if (signalReason) {
    writeManifest("interrupted", { signal: signalReason, exitCode: result.code, leaseExpiresAt: null });
    return 130;
  }
  if (result.code !== 0 && spec.launch.exitAfterReadySeconds === 0) {
    if (healthFailureReason) throw new Error(healthFailureReason);
    fail("DESKTOP_FAILED", `desktop exited ${result.code}`);
  }
  writeManifest("stopped", { stoppedAt: nowIso(), exitCode: 0, leaseExpiresAt: null });
  return 0;
}

async function handleSignal(signal) {
  signalReason = signal;
  try {
    await stopActiveChild(`signal-${signal}`);
  } catch (error) {
    console.error(`[rdcode-runner] signal cleanup failed: ${error.message}`);
  }
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  NodeProcess.once(signal, () => void handleSignal(signal));
}

let exitCode = 1;
try {
  exitCode = await main();
} catch (error) {
  stopHeartbeat();
  if (manifest) {
    try {
      await stopActiveChild("failure");
      writeManifest(signalReason ? "interrupted" : "failed", { error: error.message, leaseExpiresAt: null });
    } catch (manifestError) {
      console.error(`[rdcode-runner] Failed to persist failure: ${manifestError.message}`);
    }
  }
  console.error(`[rdcode-runner] ${error.message}`);
} finally {
  releaseCheckoutLock();
}
NodeProcess.exitCode = exitCode;
'''
