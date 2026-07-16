# @tutti-os/workspace-file-preview

Shared, host-neutral file preview helpers for workspace features.

This package owns file preview classification, safe byte handling, text
decoding, image mime resolution, and byte-limit helpers. Host adapters remain
responsible for reading bytes from the local workspace.

It also exposes a small React preview surface for consumers that want the shared
image, text, loading, and readonly rendering shell while keeping host-specific
icons and localized copy outside this package.
