import { defineConfig } from "tsup";

export default defineConfig({
  clean: true,
  dts: true,
  entry: {
    index: "src/index.ts",
    "contracts/index": "src/contracts/index.ts",
    "i18n/index": "src/i18n/index.ts",
    "react/index": "src/react/index.ts",
    "workbench/index": "src/workbench/index.ts"
  },
  external: ["react", "react-dom"],
  format: ["esm"],
  sourcemap: true
});
