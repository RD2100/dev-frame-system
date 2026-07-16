import assert from "node:assert/strict";
import test from "node:test";
import { installWorkspaceAppInteractionForwarding } from "./workspaceAppInteractionForwarding.ts";

test("workspace app interaction forwarding sends passive Browser Node host pings", () => {
  const scope = new FakeWindowScope();
  const sent: Array<{ channel: string; payload: unknown }> = [];

  const dispose = installWorkspaceAppInteractionForwarding({
    scope: scope.asWindow(),
    sendToHost(channel, payload) {
      sent.push({ channel, payload });
    }
  });

  assert.deepEqual(scope.document.eventTypes(), [
    "pointerdown",
    "focusin",
    "keydown"
  ]);
  assert.deepEqual(scope.document.options(), [
    { capture: true, passive: true },
    { capture: true, passive: true },
    { capture: true, passive: true }
  ]);

  scope.document.dispatch("pointerdown");
  scope.document.dispatch("focusin");
  scope.document.dispatch("keydown");

  assert.deepEqual(sent, [
    {
      channel: "browser-node:guest-interaction",
      payload: { type: "pointerdown" }
    },
    {
      channel: "browser-node:guest-interaction",
      payload: { type: "focusin" }
    },
    {
      channel: "browser-node:guest-interaction",
      payload: { type: "keydown" }
    }
  ]);

  dispose();
  assert.deepEqual(scope.document.eventTypes(), []);
});

class FakeWindowScope {
  readonly document = new FakeDocument();

  asWindow(): Window {
    return this as unknown as Window;
  }
}

class FakeDocument {
  private readonly records: Array<{
    listener: EventListener;
    options: unknown;
    type: string;
  }> = [];

  addEventListener(
    type: string,
    listener: EventListener,
    options?: unknown
  ): void {
    this.records.push({ listener, options, type });
  }

  removeEventListener(type: string, listener: EventListener): void {
    const index = this.records.findIndex(
      (record) => record.type === type && record.listener === listener
    );
    if (index >= 0) {
      this.records.splice(index, 1);
    }
  }

  dispatch(type: string): void {
    for (const record of this.records) {
      if (record.type === type) {
        record.listener(new Event(type));
      }
    }
  }

  eventTypes(): string[] {
    return this.records.map((record) => record.type);
  }

  options(): unknown[] {
    return this.records.map((record) => record.options);
  }
}
