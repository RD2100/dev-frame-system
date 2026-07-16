import assert from "node:assert/strict";
import test from "node:test";
import { isRichTextImeComposing } from "./richTextIme.ts";

test("rich text IME helper detects standard composition state", () => {
  assert.equal(isRichTextImeComposing({ isComposing: true }), true);
  assert.equal(
    isRichTextImeComposing({ nativeEvent: { isComposing: true } }),
    true
  );
});

test("rich text IME helper detects keyCode and which fallbacks", () => {
  assert.equal(isRichTextImeComposing({ keyCode: 229 }), true);
  assert.equal(isRichTextImeComposing({ which: 229 }), true);
  assert.equal(isRichTextImeComposing({ nativeEvent: { keyCode: 229 } }), true);
  assert.equal(isRichTextImeComposing({ nativeEvent: { which: 229 } }), true);
});

test("rich text IME helper ignores ordinary key events", () => {
  assert.equal(isRichTextImeComposing({ keyCode: 13 }), false);
});
