import assert from "node:assert/strict";
import test from "node:test";

import {
  computeNextStablePackageReleaseVersion,
  formatStablePackageReleaseTag,
  parseStablePackageReleaseTag,
  parseStablePackageReleaseVersion
} from "./package-release-version.mjs";

test("starts stable package releases at 0.0.1 when no tags exist", () => {
  assert.equal(computeNextStablePackageReleaseVersion([]), "0.0.1");
});

test("increments the highest 0.0.x package release tag", () => {
  assert.equal(
    computeNextStablePackageReleaseVersion([
      "packages-v0.0.2",
      "packages-v0.0.5",
      "packages-v0.0.3"
    ]),
    "0.0.6"
  );
});

test("rejects unsupported stable package release tags", () => {
  assert.throws(
    () => computeNextStablePackageReleaseVersion(["packages-v0.1.0"]),
    /Unsupported package release tags/
  );
});

test("formats and parses stable package release tags", () => {
  assert.equal(formatStablePackageReleaseTag("0.0.7"), "packages-v0.0.7");
  assert.deepEqual(parseStablePackageReleaseTag("packages-v0.0.7"), {
    patch: 7,
    version: "0.0.7"
  });
});

test("rejects unsupported stable package release versions", () => {
  assert.equal(parseStablePackageReleaseVersion("0.1.0"), null);
  assert.equal(parseStablePackageReleaseVersion("1.0.0"), null);
});
