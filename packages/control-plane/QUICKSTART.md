# Control Plane Quickstart

This quickstart starts from a clone of `RD2100/dev-frame-system`.

## 1. Install the CLI

```powershell
git clone https://github.com/RD2100/dev-frame-system.git
cd dev-frame-system
cd .\packages\control-plane
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## 2. Check the package

```powershell
devframe doctor
```

From the repository root, run the public checks:

```powershell
cd ..\..
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

## 3. Initialize a local workflow project

```powershell
cd .\packages\control-plane
devframe init code_project D:\tmp\demo-project
```

This writes the starter workflow files into the target project.

## 4. Run a dry pipeline

```powershell
cd D:\tmp\demo-project
devframe run --pipeline PIPELINE.yaml
```

The default runner validates and prints the pipeline stages without performing
live external effects.

## 5. Route work through rdgoal

In external-brain chat, use `/rdgoal <project> <goal>`. In a shell, use the
installed `rdgoal` command:

```powershell
rdgoal "D:\tmp\demo-project" "Build the MVP" --digest
```

`rdgoal` writes controller runtime state outside the public repository. Use
`--runtime-dir` for an explicit local runtime location and `--contracts-dir` for
an explicit project-contract directory. Without `--contracts-dir`, the contract
is created under `D:\tmp\demo-project\rules\project-contracts`.

`--apply-rdinit` requires a source checkout with the full root bootstrap assets.
Wheel installs can still create dispatch packets, but will report
`bootstrap_unavailable` if those assets are not present.

## 6. Consume a dispatch packet

Use the local dry-run worker first:

```powershell
rdgoal worker "C:\Users\you\.devframe-runtime\rdgoal-outbox\demo-project\<packet-id>"
```

When a real runner is ready, use the command worker:

```powershell
rdgoal worker "C:\Users\you\.devframe-runtime\rdgoal-outbox\demo-project\<packet-id>" `
  --command python -m your_worker_module
```

The worker receives `RDGOAL_TASKSPEC_JSON`, `RDGOAL_PACKET_JSON`, and
`RDGOAL_REPORT_PATH` environment variables and must produce an ExecutionReport.
Worker exit code is non-zero for `blocked`, `failed`, or unknown report states.

## 7. Review the runtime digest

```powershell
rdgoal digest
```

The digest is rebuilt from runtime files, so it can show decisions and worker
ExecutionReports across separate CLI invocations.
