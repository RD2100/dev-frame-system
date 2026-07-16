import assert from "node:assert/strict";
import test from "node:test";
import { isDesktopDevelopmentRuntime } from "./runtimeEnvironment.ts";

test("isDesktopDevelopmentRuntime follows explicit TUTTI_ENV before NODE_ENV", () => {
  assert.equal(
    isDesktopDevelopmentRuntime({
      tuttiEnv: "development",
      nodeEnv: "production"
    }),
    true
  );
  assert.equal(
    isDesktopDevelopmentRuntime({
      tuttiEnv: "production",
      nodeEnv: "development"
    }),
    false
  );
});

test("isDesktopDevelopmentRuntime falls back to NODE_ENV when TUTTI_ENV is unset", () => {
  assert.equal(
    isDesktopDevelopmentRuntime({
      tuttiEnv: undefined,
      nodeEnv: "development"
    }),
    true
  );
  assert.equal(
    isDesktopDevelopmentRuntime({
      tuttiEnv: "",
      nodeEnv: "production"
    }),
    false
  );
});
