import assert from "node:assert/strict";
import test from "node:test";

import {
  collectWorkspaceRuntimeDependencyNames,
  isPublicReleaseWorkspacePackage,
  validateReleasePackageSelection
} from "./npm-release-packages.mjs";

function createPackageConfig(name, manifest) {
  return {
    directory: `packages/test/${name}`,
    manifest,
    manifestPath: `packages/test/${name}/package.json`,
    name
  };
}

test("identifies public release workspace packages", () => {
  assert.equal(
    isPublicReleaseWorkspacePackage({
      private: false,
      publishConfig: { access: "public" }
    }),
    true
  );
  assert.equal(
    isPublicReleaseWorkspacePackage({
      private: true,
      publishConfig: { access: "public" }
    }),
    false
  );
  assert.equal(
    isPublicReleaseWorkspacePackage({
      private: false,
      publishConfig: { access: "restricted" }
    }),
    false
  );
});

test("collects runtime dependencies on workspace packages only", () => {
  const packageMap = new Map([
    [
      "@tutti-os/ui-system",
      createPackageConfig("@tutti-os/ui-system", {
        private: false,
        publishConfig: { access: "public" }
      })
    ],
    [
      "@tutti-os/ui-i18n-runtime",
      createPackageConfig("@tutti-os/ui-i18n-runtime", {
        private: false,
        publishConfig: { access: "public" }
      })
    ]
  ]);

  assert.deepEqual(
    [
      ...collectWorkspaceRuntimeDependencyNames(
        {
          dependencies: {
            "@tutti-os/ui-system": "workspace:*",
            react: "^19.1.0"
          },
          peerDependencies: {
            "@tutti-os/ui-i18n-runtime": "workspace:*"
          },
          devDependencies: {
            "@tutti-os/config-tsconfig": "workspace:*"
          }
        },
        packageMap
      )
    ].sort(),
    ["@tutti-os/ui-i18n-runtime", "@tutti-os/ui-system"]
  );
});

test("rejects public workspace packages that are missing from the release group", () => {
  const packageMap = new Map([
    [
      "@tutti-os/workbench-surface",
      createPackageConfig("@tutti-os/workbench-surface", {
        private: false,
        publishConfig: { access: "public" }
      })
    ],
    [
      "@tutti-os/ui-i18n-runtime",
      createPackageConfig("@tutti-os/ui-i18n-runtime", {
        private: false,
        publishConfig: { access: "public" }
      })
    ]
  ]);

  assert.throws(
    () =>
      validateReleasePackageSelection(packageMap, [
        "@tutti-os/workbench-surface"
      ]),
    /Public workspace packages missing/
  );
});

test("rejects runtime workspace dependencies outside the release group", () => {
  const packageMap = new Map([
    [
      "@tutti-os/workbench-surface",
      createPackageConfig("@tutti-os/workbench-surface", {
        private: false,
        publishConfig: { access: "public" },
        dependencies: {
          "@tutti-os/ui-i18n-runtime": "workspace:*"
        }
      })
    ],
    [
      "@tutti-os/ui-i18n-runtime",
      createPackageConfig("@tutti-os/ui-i18n-runtime", {
        private: true
      })
    ]
  ]);

  assert.throws(
    () =>
      validateReleasePackageSelection(packageMap, [
        "@tutti-os/workbench-surface"
      ]),
    /must not depend on workspace runtime packages outside the fixed release group/
  );
});

test("accepts a complete fixed release group", () => {
  const packageMap = new Map([
    [
      "@tutti-os/workbench-surface",
      createPackageConfig("@tutti-os/workbench-surface", {
        private: false,
        publishConfig: { access: "public" },
        dependencies: {
          "@tutti-os/ui-i18n-runtime": "workspace:*",
          "@tutti-os/ui-system": "workspace:*"
        }
      })
    ],
    [
      "@tutti-os/ui-i18n-runtime",
      createPackageConfig("@tutti-os/ui-i18n-runtime", {
        private: false,
        publishConfig: { access: "public" }
      })
    ],
    [
      "@tutti-os/ui-system",
      createPackageConfig("@tutti-os/ui-system", {
        private: false,
        publishConfig: { access: "public" }
      })
    ]
  ]);

  assert.doesNotThrow(() =>
    validateReleasePackageSelection(packageMap, [
      "@tutti-os/workbench-surface",
      "@tutti-os/ui-i18n-runtime",
      "@tutti-os/ui-system"
    ])
  );
});
