const stablePackageReleaseTagPrefix = "packages-v";
const stablePackageReleaseVersionPattern = /^0\.0\.(?<patch>\d+)$/;

export function computeNextStablePackageReleaseVersion(tagNames) {
  const stableVersions = [];
  const invalidTags = [];

  for (const tagName of tagNames) {
    if (!tagName.startsWith(stablePackageReleaseTagPrefix)) {
      continue;
    }

    const version = parseStablePackageReleaseTag(tagName);
    if (!version) {
      invalidTags.push(tagName);
      continue;
    }

    stableVersions.push(version);
  }

  if (invalidTags.length > 0) {
    throw new Error(
      `Unsupported package release tags: ${invalidTags.join(", ")}`
    );
  }

  if (stableVersions.length === 0) {
    return "0.0.1";
  }

  const nextPatch =
    Math.max(...stableVersions.map((version) => version.patch)) + 1;
  return `0.0.${nextPatch}`;
}

export function formatStablePackageReleaseTag(version) {
  if (!parseStablePackageReleaseVersion(version)) {
    throw new Error(`Unsupported package release version: ${version}`);
  }

  return `${stablePackageReleaseTagPrefix}${version}`;
}

export function parseStablePackageReleaseTag(tagName) {
  if (!tagName.startsWith(stablePackageReleaseTagPrefix)) {
    return null;
  }

  return parseStablePackageReleaseVersion(
    tagName.slice(stablePackageReleaseTagPrefix.length)
  );
}

export function parseStablePackageReleaseVersion(version) {
  const match = stablePackageReleaseVersionPattern.exec(version);

  if (!match?.groups) {
    return null;
  }

  return {
    patch: Number(match.groups.patch),
    version
  };
}
