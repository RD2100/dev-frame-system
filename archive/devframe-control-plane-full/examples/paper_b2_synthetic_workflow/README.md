# PAPER-B2 Synthetic Workflow

This fixture documents the minimal PAPER-B2 scenario requested by web GPT.

The workflow is synthetic-only. It does not contain real paper full text,
private user text, raw transcripts, external upload, browser profile data,
cookies, or session data.

Positive path:
- initialize a `paper_iteration` project from the existing template
- run the real reference paper stage functions through `pre_submission_check`
- require `PAPER_TASK_VALIDATION.directory.json` and `PAPER_TASK_VALIDATION.zip.json`
- expect `pre_submission_check` to complete

Negative path:
- run the same real stage path through evidence pack generation
- remove `paper_task/REDACTION_REPORT.yaml` from the generated ZIP
- run `pre_submission_check`
- expect fail-closed with `paper_task_evidence_pack_paper_task_validator_failed`

This fixture is not a closure claim. PAPER-B2 remains `ready_for_review` until
web GPT accepts a closure evidence pack and the accepted review is bound to
the appropriate ledger/state.
