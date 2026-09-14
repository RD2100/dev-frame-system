---
description: Proposed bounded Obsidian memory with project isolation, safe append, and optional availability.
---

# Detailed Design Part 3: Obsidian Memory

English | [中文](detailDesign-part3.zh.md)

## Summary

This reference specifies optional long-term knowledge for the [general design](generalDesign.md). Native DSH logs own execution history; the Vault stores only selected facts, preferences, lessons, and unresolved questions. The first version uses bounded Markdown files and ordinary filesystem operations, not a new database or embedding service. Memory content is untrusted context and never grants tools, permissions, or authority.

## Table of Contents

- [Requirements and namespaces](#requirements)
- [Memory tools and limits](#tools)
- [Read and append behavior](#storage)
- [Trust, conflicts, and freshness](#trust)
- [Failure behavior and integration](#failure)

<a id="requirements"></a>

## Requirements and namespaces

The user explicitly selects a Vault root and enables writes before any append operation. Read-only mode is valid. Resolve the project's native workspace identity from the calling session, not from a model-supplied directory or another project's ID.

| ID | Required behavior | Acceptance owner |
| --- | --- | --- |
| `R3.1` | Recall bounded content from the caller's project and explicitly allowed user memory. | [AT3-01, AT3-02](testAndAcceptance.md#part3) |
| `R3.2` | Create notes without overwrite/escape/duplicate retries and preserve externally changed files. | [AT3-03, AT3-04, AT3-09](testAndAcceptance.md#part3) |
| `R3.3` | Preserve provenance and distinguish confirmed facts from inference or stale context. | [AT3-05, AT3-06](testAndAcceptance.md#part3) |
| `R3.4` | Keep ordinary development usable when optional memory fails; report write failures honestly. | [AT3-07, AT3-08](testAndAcceptance.md#part3) |

The first version is a DevFrame-managed append-only note area, not general synchronization of an editable Obsidian Vault. Use a dedicated subtree, generate filenames from safe host IDs, and do not scan or reorganize the whole Vault. Human edits, moves, and renames are handled as described below rather than silently imported.

```text
<vault>/devframe-memory/
  user/<noteId>.md
  projects/<workspaceId>/<noteId>.md
```

Project controllers may append their own project notes after append is enabled. Workers and reviewers may read only their allowed namespaces. A user-wide preference is written only from an explicit human confirmation referenced by the note; neither Shadow nor a controller can promote its own inference into a confirmed preference.

<a id="tools"></a>

## Memory tools and limits

The proposed interface has three tools. `scope` selects `project` or `user`; it does not accept an arbitrary path. Returned excerpts include note identity, provenance, freshness, and truncation information.

| Tool | Input | Output |
| --- | --- | --- |
| `memory_search` | `scope`, bounded query, optional result limit below the configured maximum. | Matching note IDs, short excerpts, dates, and `truncated`; scope checks happen before reading note content. |
| `memory_read` | `scope`, host-issued `noteId`. | Bounded note content and source metadata; reject unknown IDs and links outside the allowed namespace. |
| `memory_append` | `scope`, stable source event reference, note kind, bounded body, optional superseded note ID. | `created`, `already_exists`, or an explicit failure; role, consent, source, and content checks are host-owned. |

Initial configurable limits are 8 KiB per note, 16 KiB total returned content, 10 search results, and 200 candidate files per search. Count encoded UTF-8 bytes and truncate only at valid character boundaries. Reaching the candidate limit returns partial coverage explicitly; it must not claim that no matching knowledge exists anywhere.

Search begins with project-local files plus explicitly allowed user notes, using deterministic filename/metadata selection and bounded text matching. No background indexing process is required. Larger corpora require a measured retrieval problem before adding an index or vector store.

Notes carry host-canonicalized **entity tags**: the model proposes the subjects a note is about, the host normalizes them (bounded, single-subject shape, secret-screened) and auto-anchors every project note to its workspace. `memory_search` accepts an entity filter, so "everything about X" is one deterministic lookup; the supersession chain supplies the validity window. The tags are a knowledge graph's entity anchoring without a graph database, an extraction pipeline, or relation edges between entities — notes themselves are the fact nodes, and richer structure waits for a measured need.

Transient read/append failures use the bounded retry policy in [Part 4](detailDesign-part4.md#limits), retaining the same operation identity and candidate content. Permission errors, conflicts, and incomplete notes are not retried automatically.

<a id="storage"></a>

## Read and append behavior

Each note has a schema version, note ID, namespace, kind (`fact`, `preference`, `lesson`, or `question`), creation time, source session/event reference, optional source snapshot, and assertion status (`confirmed`, `observed`, or `inferred`). A content digest identifies the exact stored body. The host derives identity and source fields; a model supplies candidate prose, not authoritative metadata.

1. Resolve the configured Vault and namespace; reject traversal, unexpected symlink/reparse components, and paths resolving outside the allowed root.
2. Validate role and append consent, source event ownership, supported schema, note size, and content screening.
3. Derive a stable note ID from namespace and source event; retain the candidate body across retries rather than regenerating it. Check for a committed receipt before creating: if present, validate its recorded path and digest and return `already_exists`, `memory_changed`, or `memory_missing` without recreating the file.
4. Create the file exclusively using the supported filesystem provider's create-only operation; never truncate or replace an existing note.
5. Flush and close the file, then durably record its expected relative path and full-file digest in the DSH session log before returning `created`. A crash before that receipt leaves unconfirmed content, not a confirmed memory.

The minimal implementation may use exclusive create (`wx`) and a completeness digest. A reader also compares the full file against the committed session receipt, which cannot be replaced by editing the note's own metadata. Without a receipt, matching complete candidate content may be confirmed by the original append retry; partial content remains `incomplete_note` and is preserved for explicit repair.

| External change | First-version behavior |
| --- | --- |
| User edits generated body or metadata | Report `memory_changed`, preserve the file, and exclude it from automatic confirmed recall. A digest mismatch proves a change, not whether it is a correction or corruption. |
| User moves, renames, or deletes the file | Report `memory_missing` at its recorded path; do not chase files across namespaces, recreate it automatically, or claim synchronization. |
| User explicitly submits a correction in conversation | After the required confirmation, append a new sourced note that supersedes the old one; never overwrite the edited file. |

A move/rename watcher, automatic external-edit import, and bidirectional synchronization are out of scope. A confirmed file that disappears must not be recreated merely because the original append is retried. `AT3-09` exercises these user operations on temporary files.

If the destination already exists and its complete content matches, return `already_exists`; if it differs, return `memory_conflict` without modifying either version. Concurrent appends with the same source event must produce at most one complete note. A host-side mutex is useful but is not a replacement for exclusive filesystem creation.

Validate create-only and path containment behavior on the deployed filesystem, including supported Windows paths. If an adapter cannot provide the required operation, disable append and expose read-only memory instead of falling back to an unrestricted shell write. These checks constrain agent-selected paths; they are not a promise against malicious concurrent filesystem mutation by another privileged local process.

<a id="trust"></a>

## Trust, conflicts, and freshness

Memory is context, not instruction. Label retrieved notes with source and trust status before model injection, and record that injection in the session event log so it is reconstructable. A note saying to ignore permissions, run a command, or change project scope remains quoted data and cannot change runtime policy.

Confirmed user preferences require a direct human source. Project observations retain their snapshot/version scope. Inferred lessons stay marked as inference; a numeric model confidence score is not proof. When a referenced snapshot differs from the current project, mark the observation potentially stale and verify it before acting on it.

Conflicting notes are shown together unless an authorized newer note explicitly supersedes an older one. Supersession is append-only and namespace-local; it does not erase the old source. Do not choose a winning fact solely because a model wrote it more recently.

Never copy full transcripts, secrets, credentials, raw environment dumps, or unnecessary personal data into the Vault. Prefer a short approved conclusion with local source references. Content screening reduces accidental leakage but is not a guarantee; suspicious content is rejected without echoing the suspected secret into logs.

<a id="failure"></a>

## Failure behavior and integration

Recall runs once at the beginning of a project task when enabled, with explicit additional reads only when needed. Reuse the controller's final task summary as a candidate project note after acceptance; do not create a separate reflection agent or another automatic model conversation.

| Failure | Required behavior |
| --- | --- |
| Vault unavailable or not configured | Return `memory_unavailable` with a bounded explanation; ordinary development may continue without recall. |
| Read-only Vault or append disabled | Preserve the candidate summary in native task output; do not claim it was saved to Obsidian. |
| Oversized, malformed, unsafe, or secret-bearing note | Reject or exclude it with a specific reason; do not use a permissive fallback. |
| Retry exhaustion or note conflict | Keep a visible warning and stable candidate reference; require an explicit repair decision. |

Memory failure does not undo a valid code acceptance. Conversely, if the user's primary task is to save or retrieve memory, that failure is a task failure; optional availability must not turn an unsuccessful memory request into success.

## Dev Note

Borrow bounded-reading, create-only, and conflict tests from the old repository as behavior examples, not its publication/approval framework. This feature is accepted by [AT3-*](testAndAcceptance.md#part3), including fresh-session recall and real filesystem failures, not by a mock-only note adapter.
