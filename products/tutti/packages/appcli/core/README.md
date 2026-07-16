# App CLI Core

`packages/appcli/core` owns the reusable Go implementation of the App CLI
protocol contract used by workspace apps.

The package is intentionally limited to protocol-level behavior:

- `tutti.app.cli.v1` manifest reading and validation
- command capability construction from a manifest and host-provided app metadata
- manifest input normalization
- `tutti.app.cli.invoke.v1` HTTP invoke envelopes
- handler response decoding and output contract validation
- scope conflict and reserved-scope state calculation

Host products keep their own workspace lookup, durable state, app package
metadata, runtime startup, and user-facing status DTO adapters outside this
module. Tutti daemon integration lives in `services/tuttid/service/cli/appcli`.

The protocol strings still use the frozen Tutti App CLI contract for backwards
compatibility with existing app manifests and handlers. That does not make this
module a Tutti daemon business layer; consumers such as TSH can reuse the
protocol core while supplying their own host adapters.
