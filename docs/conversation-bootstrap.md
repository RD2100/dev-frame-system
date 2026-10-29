# Conversation Bootstrap — Official Handoff Flow

## T3 — Solidified Standard Protocol

The official handoff flow was validated in T2 and solidified in T3.

## Official Flow

```
1. GPT (with full context) writes HANDOFF.md (10,000+ chars, self-contained)
2. Agent verifies HANDOFF.md exists
3. Agent uploads HANDOFF.md as .md FILE ATTACHMENT (not inline text)
4. Agent includes bootstrap prompt asking new conversation to read the file
5. Agent clicks send
6. Agent captures new conversation reply
7. Agent verifies handoff_understood=yes
8. If handoff_verified=false → fail-closed, no execution
```

## Why File Attachment

- File upload preserves the document as a discrete artifact
- Inline text paste is fragile and loses formatting
- The new conversation can download and reference the file
- This matches the evidence-first protocol (ZIP packs as file attachments)

## CLI

```bash
# Generate skeleton (structure only — GPT must fill substance)
devframe handoff generate

# Validate handoff document
devframe handoff validate HANDOFF.md

# Dry-run transfer (prints what would happen)
devframe handoff transfer --to new-conversation

# Live transfer (requires CDP + safety flags)
devframe handoff transfer --to https://chatgpt.com/c/<id>
```

## Safety

- handoff_verified=false → fail-closed
- No state mutation
- No guard removal
- No evidence cleanup
- Transfer is dry-run by default
