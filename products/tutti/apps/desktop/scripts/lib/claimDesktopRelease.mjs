import { resolveDesktopRelease } from "./resolveDesktopRelease.mjs";

function isExplicitStrategy(strategy) {
  return strategy === "explicit_tag" || strategy === "explicit_version";
}

export async function claimDesktopRelease({
  currentVersion,
  explicitTag = "",
  explicitVersion = "",
  listTags,
  maxAttempts = 20,
  reserveTag,
  strategy
}) {
  if (typeof listTags !== "function") {
    throw new Error("listTags must be provided");
  }
  if (typeof reserveTag !== "function") {
    throw new Error("reserveTag must be provided");
  }

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const release = resolveDesktopRelease({
      currentVersion,
      explicitTag,
      explicitVersion,
      strategy,
      tags: await listTags()
    });

    if (await reserveTag(release.tag)) {
      return release;
    }

    if (isExplicitStrategy(strategy)) {
      throw new Error(`Release tag already exists: ${release.tag}`);
    }
  }

  throw new Error(
    `Unable to reserve a unique release tag after ${maxAttempts} attempts`
  );
}
