# Agent Note: Client composition smoke assembles feature plugins over the jsdom bench

Status: implemented

English | [中文](2026-09-05-client-composition-smoke-package.zh.md)

## Problem

A client feature spec that renders one component against hand-built props cannot see whether the parts compose: the plugin's `apply` wiring, the slot-ledger registration, the locale-registry seat, and the rendered row all sit behind the mount boundary, and the browser snapshot lane that does observe them is a Chromium gate that many hosts cannot run. Acceptance work that must verify an assembled flow — the sidebar session list reaching a row's actions menu and its Session-ID dialog — therefore had no host-portable, keyless home, and parking such a spec inside one feature package's `tests/` makes every parallel effort edit the same directory.

## Decision

`packages/test-support/composition-smoke` owns the assembled-layer smoke tier for the web client. Its `mountComposition()` wraps the [client test runtime](../../../../packages/test-support/client-runtime/README.md) bench in one call: assemble the real Cordis `Context`, `SlotRegistry`, renderer, and `ui-session` adapter over the typed Controller doubles, run a spec-owned `provide` callback, then mount one feature plugin on a live fiber behind the bench's fail-loud service precheck. The package's suite mounts the real ui-workspace client plugin this way and asserts the composed surface: the session list renders through the production renderer, the row actions menu opens the Session-ID dialog, the slot ledger carries the entry with its locale namespace and declared child hole, the locale registry binds the namespace, the two shipped dictionaries stay key-identical, and disposal unregisters the entry. The suite runs in the default unit lane under the per-file jsdom pragma, so every host with Node runs it without a server, a key, or a browser.

## Alternatives considered

**Put the composed spec in the feature package's tests.** Rejected: feature-package specs own component behavior against hand-built props, and a composed-mount spec there turns the package's tests directory into a shared editing surface for every cross-package effort; support tier is where this bench already lives.

**Add a jsdom spec under `apps/web/tests`.** Rejected: that directory is the browser snapshot lane, and the app assembly pulls the generated Host-for-Client Remote contribution that exists only in built `lib`; the bench covers the same production plugin machinery without either cost.

**Assert only the export surface and dictionary files statically.** Rejected: importable exports prove nothing about composition — a mount that registers nothing or a dialog that never opens passes a static check; the value of this tier is the observed assembled behavior.

## Consequences

Assembled client regressions that unit specs and hand-built props cannot see now fail in the plain unit lane on every host, and acceptance checklists can cite one keyless command as composition evidence. The cost is one more support package whose tsconfig mirrors the client-runtime reference closure, and a bench whose doubles still fail loud on unstubbed verbs — the smoke stays narrow by design: it pins composition, not feature breadth, which remains with the feature specs and the browser snapshot lane.
