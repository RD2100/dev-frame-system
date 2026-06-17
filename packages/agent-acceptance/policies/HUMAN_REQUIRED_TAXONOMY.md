# Human Required Taxonomy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode, GPT reviewer, any automation agent
> Version: 1.0.0

---

## Purpose

When `business_decision: human_required` is set, the reason MUST be classified using one of the following taxonomy codes. This ensures automation correctly identifies WHY human input is needed and WHAT the human must do.

---

## Taxonomy Categories

### 1. missing_baseline

**Definition**: The baseline (starting commit, branch, file state) cannot be verified.

**Examples**:
- No git commit hash available
- Starting state files not found
- Expected artifacts absent

**Required Human Action**: Provide or confirm the baseline (e.g., specify commit hash, verify file existence).

---

### 2. destructive_action

**Definition**: The next action would delete, move, rename, or clean files.

**Examples**:
- Deleting files or directories
- Moving files between directories
- Renaming files
- Cleaning worktrees
- `git reset --hard`

**Required Human Action**: Explicitly confirm the destructive action is intended.

---

### 3. sensitive_config

**Definition**: The action touches sensitive configuration (credentials, secrets, env vars, permissions).

**Examples**:
- Modifying `.env` files
- Changing secret values
- Altering access control rules
- Modifying governance rules

**Required Human Action**: Confirm the configuration change and verify no secrets are exposed.

---

### 4. evidence_overwrite

**Definition**: The action would overwrite historical evidence (GPT review results, attestations, audit records).

**Examples**:
- Overwriting `GPT_REVIEW_RESULT.md`
- Modifying `FLOW_OUTCOME.json` from a past round
- Altering audit records

**Required Human Action**: Confirm overwrite is intentional and the old evidence is preserved.

---

### 5. scope_expansion

**Definition**: The action would go beyond the approved scope (modify files outside task spec, add new capabilities).

**Examples**:
- Modifying files not in `allowed_files`
- Adding new directories outside task spec
- Registering new capabilities without approval

**Required Human Action**: Approve scope expansion or reject it.

---

### 6. ambiguous_authority

**Definition**: It is unclear who has authority to make this decision (ownership boundary unclear).

**Examples**:
- Changes at the boundary between agent-acceptance and dev-frame-opencode
- Cross-project configuration changes
- Decisions affecting multiple projects

**Required Human Action**: Clarify authority and designate decision-maker.

---

### 7. external_secret

**Definition**: The action requires or could expose external secrets (API keys, tokens, passwords).

**Examples**:
- Uploading files to external services
- Using API keys in automation
- Transmitting data containing secrets

**Required Human Action**: Verify no secrets are present or provide the secret through secure channels.

---

### 8. manual_attestation_required

**Definition**: A human must attest to a fact that cannot be verified by machine.

**Examples**:
- "I reviewed the diff and it looks correct"
- "I confirm the test output matches expected"
- "I verified the GPT reply was captured correctly"
- "I confirm the baseline is genuine"

**Required Human Action**: Provide signed attestation (date, name, statement of what was verified).

---

## Usage in FLOW_OUTCOME

```json
{
  "business_decision": "human_required",
  "required_next_action": "Human must provide attestation that baseline commit abc123 is correct",
  "human_required_reason": "missing_baseline",
  "terminal": true
}
```

## Usage in TaskSpec

```json
{
  "review_by": "human",
  "human_required_reason": "destructive_action",
  "high_risk": true,
  "terminal_conditions": {
    "terminal": true,
    "reason": "high_risk_required"
  }
}
```

---

## Precedence

When multiple taxonomy codes apply, use the most restrictive one:

`external_secret` > `destructive_action` > `evidence_overwrite` > `scope_expansion` > `sensitive_config` > `ambiguous_authority` > `missing_baseline` > `manual_attestation_required`
