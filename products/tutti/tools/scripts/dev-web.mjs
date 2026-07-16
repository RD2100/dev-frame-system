import { spawn, spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readFile, rm } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const healthPollIntervalMs = 250;
const healthTimeoutMs = 15_000;
const shutdownTimeoutMs = 5_000;

const scriptDir = dirname(fileURLToPath(import.meta.url));
const workspaceRoot = join(scriptDir, "..", "..");
const tuttidDir = join(workspaceRoot, "services", "tuttid");
const defaultsPath = join(workspaceRoot, "config", "tutti.defaults.json");
const generatedDefaults = JSON.parse(await readFile(defaultsPath, "utf8"));
const installDevCliScriptPath = join(
  workspaceRoot,
  "tools",
  "scripts",
  "install-dev-cli.mjs"
);

const stateDirOverride = process.env.TUTTI_STATE_DIR?.trim();
const stateDir = stateDirOverride || resolveDevelopmentStateRoot();
const listenerInfoPath = join(
  stateDir,
  generatedDefaults.state.runDirName,
  generatedDefaults.state.listenerInfoFileName
);
const accessToken = randomBytes(32).toString("base64url");

let shutdownStarted = false;
let exitCode = 0;

installDevCli();
generateBuiltinApps();

const daemon = spawn(resolveCommand("go"), ["run", "."], {
  cwd: tuttidDir,
  env: {
    ...process.env,
    TUTTID_ACCESS_TOKEN: accessToken,
    TUTTID_ADDR: "127.0.0.1:0",
    TUTTID_LISTENER_INFO_PATH: listenerInfoPath,
    TUTTID_LOG_OUTPUT: process.env.TUTTID_LOG_OUTPUT?.trim() || "tee",
    TUTTI_ANALYTICS_DEBUG:
      process.env.TUTTI_ANALYTICS_DEBUG?.trim() ||
      process.env.VITE_TUTTI_ANALYTICS_DEBUG?.trim() ||
      "",
    TUTTI_ENV: "development",
    TUTTI_STATE_DIR: stateDir
  },
  stdio: ["ignore", "pipe", "pipe"]
});

daemon.stdout?.on("data", (chunk) => {
  process.stdout.write(`[tuttid] ${chunk.toString()}`);
});

daemon.stderr?.on("data", (chunk) => {
  process.stderr.write(`[tuttid] ${chunk.toString()}`);
});

let vite = null;

try {
  const baseUrl = await waitForHealthyBaseUrl(
    listenerInfoPath,
    accessToken,
    () => isAlive(daemon)
  );
  const startupWorkspaceID = await resolveStartupWorkspaceID(
    baseUrl,
    accessToken
  );

  console.log(`[dev-web] tuttid backend ready at ${baseUrl}`);
  console.log(`[dev-web] State root: ${stateDir}`);
  console.log(`[dev-web] Do not open that backend URL in the browser.`);
  console.log(`[dev-web] Open the Vite Local URL printed below instead.`);
  console.log(`[dev-web] CLI endpoint ready: tutti-dev status`);
  if (startupWorkspaceID) {
    console.log(
      `[dev-web] Startup workspace is injected automatically: ${startupWorkspaceID}`
    );
  }

  vite = spawn(
    resolveCommand("pnpm"),
    ["--filter", "@tutti-os/desktop", "dev:web"],
    {
      cwd: workspaceRoot,
      env: {
        ...process.env,
        VITE_TUTTID_ACCESS_TOKEN: accessToken,
        VITE_TUTTID_BASE_URL: baseUrl,
        VITE_TUTTI_WEB_DEV: "1",
        ...(startupWorkspaceID
          ? { VITE_TUTTI_WEB_WORKSPACE_ID: startupWorkspaceID }
          : {})
      },
      stdio: "inherit"
    }
  );

  const handleSignal = async (signal) => {
    if (shutdownStarted) {
      return;
    }
    exitCode = signal === "SIGINT" ? 130 : 143;
    await shutdown(vite, daemon);
    process.exit(exitCode);
  };

  process.on("SIGINT", handleSignal);
  process.on("SIGTERM", handleSignal);

  const result = await Promise.race([
    onceExit(daemon).then(({ code, signal }) => ({
      code: code ?? (signal ? 1 : 0),
      signal,
      source: "daemon"
    })),
    onceExit(vite).then(({ code, signal }) => ({
      code: code ?? (signal ? 1 : 0),
      signal,
      source: "vite"
    }))
  ]);

  if (result.source === "daemon" && isAlive(vite) && result.code !== 0) {
    console.error("[dev-web] tuttid exited before Vite stopped.");
    exitCode = result.code || 1;
  } else {
    exitCode = result.code;
  }
} catch (error) {
  exitCode = 1;
  const message = error instanceof Error ? error.message : String(error);
  console.error(`[dev-web] failed to start: ${message}`);
} finally {
  await shutdown(vite, daemon);
  await clearListenerInfoIfOwned(listenerInfoPath, accessToken);
}

process.exit(exitCode);

function resolveDevelopmentStateRoot() {
  return join(homedir(), generatedDefaults.state.developmentDirName);
}

function installDevCli() {
  const result = spawnSync(process.execPath, [installDevCliScriptPath], {
    cwd: workspaceRoot,
    env: {
      ...process.env,
      TUTTI_ENV: "development"
    },
    stdio: "inherit"
  });
  if (result.status !== 0) {
    throw new Error(
      `install tutti-dev failed with exit code ${result.status ?? "unknown"}`
    );
  }
}

function generateBuiltinApps() {
  const result = spawnSync(resolveCommand("pnpm"), ["generate:builtin-apps"], {
    cwd: workspaceRoot,
    env: {
      ...process.env,
      TUTTI_ENV: "development"
    },
    stdio: "inherit"
  });
  if (result.status !== 0) {
    throw new Error(
      `generate builtin apps failed with exit code ${result.status ?? "unknown"}`
    );
  }
}

async function waitForHealthyBaseUrl(
  listenerInfoPathToCheck,
  token,
  isProcessAlive
) {
  const deadline = Date.now() + healthTimeoutMs;
  let lastError;

  while (Date.now() < deadline) {
    if (!isProcessAlive()) {
      throw new Error(
        `tuttid exited before health check succeeded: ${String(lastError ?? "unknown error")}`
      );
    }

    try {
      const baseUrl = await readListenerInfoBaseUrl(listenerInfoPathToCheck);
      const health = await requestJSON(new URL("/v1/health", baseUrl), token);
      if (health?.status === "ok") {
        return baseUrl;
      }
      lastError = new Error(
        `unexpected health response: ${JSON.stringify(health)}`
      );
    } catch (error) {
      lastError = error;
    }

    await sleep(healthPollIntervalMs);
  }

  throw new Error(
    `timed out waiting for tuttid health: ${String(lastError ?? "unknown error")}`
  );
}

async function resolveStartupWorkspaceID(baseUrl, token) {
  try {
    const response = await requestJSON(
      new URL("/v1/workspaces/startup", baseUrl),
      token
    );
    return response?.workspace?.id ?? null;
  } catch {
    return null;
  }
}

async function requestJSON(url, token) {
  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      authorization: `Bearer ${token}`
    },
    signal: AbortSignal.timeout(5_000)
  });

  if (!response.ok) {
    throw new Error(
      `request failed with status ${response.status} ${response.statusText}`.trim()
    );
  }

  return response.json();
}

async function readListenerInfoBaseUrl(listenerInfoPathToRead) {
  const content = await readFile(listenerInfoPathToRead, "utf8");
  const parsed = JSON.parse(content);
  if (!parsed?.addr || typeof parsed.addr !== "string") {
    throw new Error(`invalid listener info: ${content}`);
  }
  return `http://${parsed.addr}`;
}

async function clearListenerInfoIfOwned(listenerInfoPathToClear, token) {
  try {
    const content = await readFile(listenerInfoPathToClear, "utf8");
    const parsed = JSON.parse(content);
    if (parsed?.auth?.token !== token) {
      return;
    }
  } catch {
    return;
  }

  await rm(listenerInfoPathToClear, { force: true });
  await rm(`${listenerInfoPathToClear}.tmp`, { force: true });
}

function resolveCommand(command) {
  if (process.platform === "win32") {
    return `${command}.cmd`;
  }
  return command;
}

function isAlive(child) {
  if (!child) {
    return false;
  }
  return child.exitCode === null && child.signalCode === null;
}

function onceExit(child) {
  return new Promise((resolve) => {
    child.once("exit", (code, signal) => {
      resolve({ code, signal });
    });
  });
}

async function shutdown(viteChild, daemonChild) {
  if (shutdownStarted) {
    return;
  }
  shutdownStarted = true;
  await stopChild(viteChild, "SIGINT");
  await stopChild(daemonChild, "SIGTERM");
}

async function stopChild(child, signal) {
  if (!child || !isAlive(child)) {
    return;
  }

  child.kill(signal);
  await Promise.race([
    onceExit(child),
    sleep(shutdownTimeoutMs).then(() => {
      if (isAlive(child)) {
        child.kill("SIGKILL");
      }
    })
  ]);
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
