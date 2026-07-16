import { parseReleaseTag } from "./releaseConfig.mjs";

function normalizeSemverLikeVersion(value) {
  const normalized = value.trim().replace(/^v/u, "");
  return /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/u.test(normalized)
    ? normalized
    : null;
}

function normalizePrereleaseIdentifier(value) {
  return value
    .trim()
    .replace(/[^0-9A-Za-z.-]+/gu, "-")
    .replace(/^[.-]+/u, "")
    .replace(/[.-]+$/u, "");
}

export function normalizeDesktopGitDescribeVersion(value) {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!normalized) {
    return null;
  }

  const releaseVersion = parseReleaseTag(normalized);
  if (releaseVersion) {
    return releaseVersion;
  }

  const semverLike = normalizeSemverLikeVersion(normalized);
  if (semverLike) {
    return semverLike;
  }

  const prerelease = normalizePrereleaseIdentifier(normalized);
  return prerelease ? `0.0.0-${prerelease}` : null;
}

export function resolveDesktopBuildVersion({
  describeVersion = "",
  fallbackVersion = "",
  releaseTag = ""
} = {}) {
  return (
    normalizeDesktopGitDescribeVersion(releaseTag) ??
    normalizeDesktopGitDescribeVersion(describeVersion) ??
    normalizeDesktopGitDescribeVersion(fallbackVersion)
  );
}
