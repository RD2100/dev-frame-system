# CI Preflight Template

One-time setup to activate pre-commit and pre-push governance hooks.
No dependencies beyond Git 2.9+ and PowerShell.

## Install (per project)

```powershell
# Copy template files into your project
cp -r templates/ci-preflight/* <target-project>/

# Activate hooks
cd <target-project>
powershell -ExecutionPolicy Bypass -File register-hooks.ps1
```

## What it does

| Hook | When | Checks |
|------|------|--------|
| pre-commit | `git commit` | manifest auto-regen + ai_guard secret scan |
| pre-push | `git push` | ai_guard full + drift check + governance gate |

## Customize

1. `governance/expected-files.txt` — add your project's governance files
2. `governance/manifest-ignore.txt` — add temp/archive dirs to exclude
3. `hooks/pre-commit.governance.ps1` — add project-specific checks (tests, lint, etc.)
4. `hooks/pre-push.governance.ps1` — add project-specific pre-push checks

## Verify

```powershell
powershell -File ci-preflight.ps1
```

All three checks should pass on a clean working tree.

## Structure

```
templates/ci-preflight/
  hooks/
    pre-commit                    # bash entry point
    pre-commit.governance.ps1    # PowerShell logic
    pre-push                      # bash entry point
    pre-push.governance.ps1      # PowerShell logic
  governance/
    expected-files.txt            # which files to protect
    manifest-ignore.txt           # which to exclude
  register-hooks.ps1              # one-time activation
  ci-preflight.ps1                # manual pre-push check
  README.md                       # this file
```
