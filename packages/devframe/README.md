# devframe/ — controller-session foundation

English | [中文](README.zh.md)

DevFrame extensions that build on DSH's native Session, Workspace, Agent, Profile, and browser surfaces. This group keeps control identity inside the existing DSH runtime and does not own a second workbench or persistence system.

| Package | Role | ctx key |
|---|---|---|
| [`control-session/`](control-session/README.md) | Stable identity-only Global and Project Controller Sessions | `ctx.devframeControlSessions` |

The child README owns the service, durability, privacy, execution, and single-Host-process contracts.
