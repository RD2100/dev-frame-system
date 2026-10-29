# Evidence Archive Governance Policy

## Status

- evidence_cleanup_approved: false (permanently blocked)
- This policy governs archive maintenance WITHOUT deletion, movement, or renaming

## Rules

| Action | Allowed | Authorization |
|--------|---------|--------------|
| Read evidence | Yes | None |
| Index evidence | Yes | None |
| Cross-reference | Yes | None |
| Delete evidence | No | Permanently blocked |
| Move evidence | No | Permanently blocked |
| Rename evidence | No | Permanently blocked |
| Compress evidence | No | Separate auth required |
| Archive old packs | No | Separate auth required |

## Archive Health Checks

- File count monitoring (baseline at policy creation)
- Index consistency verification
- No orphan detection without classification
- All anomalies reported, none auto-resolved

## Relationship to Evidence-First

This policy implements the "append-only evidence" principle. Historical evidence is the authoritative record. Modification would break audit trails and cross-references.
