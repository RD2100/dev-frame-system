import assert from "node:assert/strict";
import test from "node:test";
import { createTerminalNodeFeature } from "./feature.ts";
import type {
  TerminalCloseGuardService,
  TerminalLaunchService,
  TerminalTransport
} from "../contracts/index.ts";

const closeGuard: TerminalCloseGuardService = {
  async check() {
    return {
      reason: "not-running",
      requiresConfirmation: false,
      status: "exited"
    };
  }
};

const launchService: TerminalLaunchService = {
  async create() {
    return {
      cwd: null,
      profileId: null,
      runtimeKind: "local",
      sessionId: "session-1",
      status: "running",
      title: "Terminal"
    };
  },
  async terminate() {
    return undefined;
  }
};

const transport: TerminalTransport = {
  async attach() {
    return undefined;
  },
  async detach() {
    return undefined;
  },
  onData() {
    return () => undefined;
  },
  onExit() {
    return () => undefined;
  },
  onState() {
    return () => undefined;
  },
  async resize() {
    return undefined;
  },
  async snapshot() {
    return { data: "" };
  },
  async write() {
    return undefined;
  }
};

test("createTerminalNodeFeature fills host-agnostic defaults", () => {
  const feature = createTerminalNodeFeature({
    closeGuard,
    launchService,
    limits: {
      maxScrollbackLines: 20
    },
    transport
  });

  assert.equal(feature.i18n.t("title"), "Terminal");
  assert.equal(feature.limits.maxScrollbackLines, 20);
  assert.equal(feature.limits.maxWriteBatchBytes, 64 * 1024);
  assert.deepEqual(
    feature.resolveTheme({
      runtimeKind: "local",
      sessionId: "session-1",
      status: "running"
    }),
    {}
  );
});
