import { spawnSync } from "node:child_process";
import path from "node:path";

export interface MacUpdaterSupportResult {
  designatedRequirement: string | null;
  message: string | null;
  supported: boolean;
}

export function extractDesignatedRequirement(
  codesignOutput: string
): string | null {
  const match = codesignOutput.match(/\bdesignated\s*=>\s*(.+)$/m);
  return match?.[1]?.trim() ?? null;
}

export function isAdhocDesignatedRequirement(
  designatedRequirement: string
): boolean {
  return /^cdhash\b/i.test(designatedRequirement.trim());
}

export function resolveMacAppBundlePath(executablePath: string): string {
  let candidate = executablePath;

  for (let index = 0; index < 5; index += 1) {
    if (candidate.endsWith(".app")) {
      return candidate;
    }

    const next = path.dirname(candidate);
    if (next === candidate) {
      break;
    }

    candidate = next;
  }

  return executablePath;
}

export function resolveMacUpdaterSupport(options: {
  appPath: string;
  platform?: NodeJS.Platform;
  spawn?: typeof spawnSync;
}): MacUpdaterSupportResult {
  const platform = options.platform ?? process.platform;
  if (platform !== "darwin") {
    return { designatedRequirement: null, message: null, supported: true };
  }

  const spawn = options.spawn ?? spawnSync;
  const result = spawn("codesign", ["-dr", "-", options.appPath], {
    encoding: "utf8"
  });

  if (result.error) {
    return {
      designatedRequirement: null,
      message:
        "macOS in-app updates require a signed build, but code signature validation is unavailable on this system.",
      supported: false
    };
  }

  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
  const designatedRequirement = extractDesignatedRequirement(output);

  if (result.status !== 0) {
    return {
      designatedRequirement,
      message:
        "macOS in-app updates require a signed build. This build is not properly signed; download the latest release manually.",
      supported: false
    };
  }

  if (!designatedRequirement) {
    return {
      designatedRequirement: null,
      message:
        "macOS in-app updates require a stable code signature. This build does not expose one; download the latest release manually.",
      supported: false
    };
  }

  if (isAdhocDesignatedRequirement(designatedRequirement)) {
    return {
      designatedRequirement,
      message:
        "macOS in-app updates require a Developer ID signature. This build is ad-hoc signed, so updates are disabled; download the latest release manually.",
      supported: false
    };
  }

  return { designatedRequirement, message: null, supported: true };
}
