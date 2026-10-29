# Rollback Plan

## Can Be Rolled Back
- Documentation files (version control)
- Route decisions
- Authorization state (conservative by default)

## Cannot Be Rolled Back
- Deleted evidence (prevented by policy)
- Overwritten evidence (prevented by policy)
- GPT conversation history

## Evidence Preservation
All files append-only or new-only. No delete/move/rename/overwrite.

## Safe Stop
- human_required on boundary violations
- Stop on review_unverified / route mismatch

## Recovery
- Retry from authorization phase
- Do not skip authorization gate
- New GPT review for scope expansion

## Human Approval Required
- Production promotion, driver replacement, guard removal, evidence cleanup
