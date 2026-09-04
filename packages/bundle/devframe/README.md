# `@deepseek-ai/dsh-devframe`

English | [中文](README.zh.md)

The thin DevFrame profile layer for DSH. Launching `dsh --profile devframe` keeps the shipped `dsh-base` and `dsh-web-app` layers intact, then mounts one Host-owned Controller Session service, a bounded headless task entry, and one native client projection. It does not replace DSH workspaces, Sessions, chat, model selection, tools, persistence, the Web server, or the API gateway.

This package is a static [`cordis.patch.yml`](cordis.patch.yml) carrier. The shipped `dsh --profile devframe` CLI acquires the Profile Host fence and automatically opens the stable Global Controller after the Loader settles. Ordinary Web arguments such as `--port` and `--host` remain owned by `dsh-web-app`; the DevFrame task provider only claims an invocation whose first app argument is `task`. A one-shot `task` invocation switches to headless mode, resolves or registers one native Workspace, and dispatches a Project Controller task for one or two bounded Goal Rounds:

```bash
DSH_DEVFRAME_EXPERIMENTAL_TASKS=1 dsh --profile devframe task --project <workspace-id-or-path> --objective "run the focused tests" --rounds 1
```

The result is a pathless JSON record containing the project, Goal, Session, and outcome identifiers. Project Controllers remain explicit outside this command. The [`client package`](../../client/ui-devframe-control-session/README.md) accepts only bounded `controller/identity` fields and never selects project roots.

## Model Experience

### Controller identity projection and bounded Goal dispatch

#### What the model sees

An identity-only open adds nothing. An explicit Host `dispatchGlobalGoal` call uses the native Goal Round prompt and normal AgentLoop request/response events in the same DSH Session; the bounded `controller/identity` event remains a Host and client projection contract and is not inserted into the system prompt or messages.

#### Token effect

Identity-only opens add no model tokens. An explicit bounded dispatch consumes the configured model's normal request tokens; the bundle adds no automatic agent loop or second task/run log.

#### KV Cache effect

Identity-only opens contribute no cache prefix. Dispatch cache behavior follows the configured provider; the bundle does not claim a cache policy.

## Known Limitations and Deferred Work

- **Bounded task entry, not an autonomous team** — the CLI can explicitly dispatch one or two Goal Rounds through a Project Controller. Global-to-Project messaging, separate Executor workers, review loops, budgets, and indefinite continuation remain deferred.
- **Experimental task gate** — task dispatch is disabled by default until the permission and audit foundation is complete. Set `DSH_DEVFRAME_EXPERIMENTAL_TASKS=1` to opt in; otherwise the command exits before publishing the task service, dispatching an AgentLoop, or writing a task Session. This tracer is not the secure total-control boundary.
- **Project open is still explicit** — the shipped profile starts the Global Controller, but a Project Controller is opened only for a selected workspace.
- **A configured model is required** — the task command fails closed when the composed profile has no usable provider/model route or the model does not return before its per-round budget.
- **One fenced DevFrame Host** — the profile fence permits one durable DevFrame writer for a `$DSH_HOME`; a second DevFrame Host fails closed. Non-DevFrame profiles retain DSH's native concurrency behavior.
