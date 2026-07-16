import assert from "node:assert/strict";
import test from "node:test";
import {
  hasAnalyticsDebugFloatingDragMoved,
  resolveAnalyticsDebugFloatingPosition
} from "./analyticsDebugFloatingPosition.ts";

test("analytics debug floating position follows pointer movement", () => {
  assert.deepEqual(
    resolveAnalyticsDebugFloatingPosition({
      floatingSize: { height: 44, width: 44 },
      pointerCurrent: { x: 180, y: 190 },
      pointerStart: { x: 120, y: 140 },
      startPosition: { left: 80, top: 90 },
      viewport: { height: 600, width: 800 }
    }),
    {
      left: 140,
      top: 140
    }
  );
});

test("analytics debug floating position stays inside viewport margin", () => {
  assert.deepEqual(
    resolveAnalyticsDebugFloatingPosition({
      floatingSize: { height: 44, width: 44 },
      pointerCurrent: { x: -100, y: -80 },
      pointerStart: { x: 20, y: 20 },
      startPosition: { left: 24, top: 24 },
      viewport: { height: 600, width: 800 }
    }),
    {
      left: 8,
      top: 8
    }
  );

  assert.deepEqual(
    resolveAnalyticsDebugFloatingPosition({
      floatingSize: { height: 44, width: 44 },
      pointerCurrent: { x: 1000, y: 900 },
      pointerStart: { x: 20, y: 20 },
      startPosition: { left: 24, top: 24 },
      viewport: { height: 600, width: 800 }
    }),
    {
      left: 748,
      top: 548
    }
  );
});

test("analytics debug floating drag starts after a small movement threshold", () => {
  assert.equal(
    hasAnalyticsDebugFloatingDragMoved({
      pointerCurrent: { x: 103, y: 104 },
      pointerStart: { x: 100, y: 100 }
    }),
    false
  );
  assert.equal(
    hasAnalyticsDebugFloatingDragMoved({
      pointerCurrent: { x: 106, y: 100 },
      pointerStart: { x: 100, y: 100 }
    }),
    true
  );
});
