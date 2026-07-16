---
"@tutti-os/ui-rich-text": minor
---

Replace the legacy `@tutti-os/ui-rich-text/at-panel` flat grouping helpers with the shared mention palette model and renderer APIs. Consumers should migrate from `buildMentionPaletteState`, `searchHelpers`, and `RichTextAt*` grouping aliases to `buildMentionPaletteModel`, `MentionPaletteFromState`, `createMentionPaletteStateAdapter`, and the `MentionPalette*` category/group types documented in the rich-text README.
