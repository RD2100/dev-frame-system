import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const rootDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@tutti-os/workspace-file-manager/services": `${rootDir}../../workspace/file-manager/src/services/index.ts`,
      "@tutti-os/workspace-file-manager": `${rootDir}../../workspace/file-manager/src/index.ts`
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"]
  }
});
