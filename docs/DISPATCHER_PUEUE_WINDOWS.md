# Machine dispatcher: Pueue on Windows

Status: Phase 1 (documentation + launchers) implemented; service activation is
a separate Phase 2 operation and has not been performed. Ratification: see
`PROPOSAL_PUEUE_MACHINE_TASK_DISPATCHER_SHANNON.md` and the task thread.

## Purpose

A persistent machine-local queue separates submitted jobs from interactive
agent applications. When an agent application dies mid-run (the MSIX
termination incident of 2026-08-25), a queued job remains under the daemon's
process tree. This protects jobs from agent-app exits, but not from user logoff
or reboot. The shared folder remains the cross-machine control plane; Pueue is
node-local execution only.

## Trust boundary (non-negotiable)

`pueued` never watches the shared folder and never executes a synced payload.
The pipeline is:

```text
READY ProjectSync TASK/REQUEST
  -> verified + interpreted by an on-machine agent
  -> checked-in launcher + checked-in task script (argument array)
  -> pueue add --group <cpu|gpu0> -- <launcher command>
  -> pueued runs it; folder traffic plays no role until results publish
```

Malformed or UNVERIFIED payloads cannot cause local execution, because the
queue consumes only commands an agent explicitly constructed after
verification.

## Release pinning (v4.0.4)

Pinned release: **v4.0.4**. Official source only:
`https://github.com/Nukesor/pueue/releases/tag/v4.0.4`

The Windows release ships two separate executables (not a zip), each with a
GitHub-published SHA-256 digest. Pin both; Phase 2 must compare the
downloaded files against these upstream digests AND record locally computed
values:

```text
pueue-x86_64-pc-windows-msvc.exe
  https://github.com/Nukesor/pueue/releases/download/v4.0.4/pueue-x86_64-pc-windows-msvc.exe
  sha256 28b0756d54ec16ce13d78b251d086aa62e0057089cb27f793cd649f9762b996a

pueued-x86_64-pc-windows-msvc.exe
  https://github.com/Nukesor/pueue/releases/download/v4.0.4/pueued-x86_64-pc-windows-msvc.exe
  sha256 aafa05e2f26cda9aff3eeb9be261e8f9f67752d1e9bb7fbcb47318e35c52ab1d
```

A locally computed digest recorded after download is not an authenticity pin
by itself; agreement with the release-published value is required before
installation. Also record the pinned build's `pueued --help` output
alongside this table.

## Service installation (Phase 2)

Use Pueue 4.0+'s **native Windows service support only**. Registering a
console daemon directly with the SCM fails with Error 1053 - the process
does not implement the Windows service protocol (upstream issue
Nukesor/pueue#344). Generic `sc.exe create` wrappers are not an option here.

```powershell
pueued [-c <config>] [-p <profile>] service install
pueued service start
Get-Service -Name pueued     # v4.0.4 has no `service status` subcommand
# or: sc.exe query pueued
pueued service stop
pueued service uninstall
```

Run installation commands from an elevated shell. Pueue installs a LocalSystem
SCM wrapper which launches `pueued` with the active interactive user's token.
Do not change the service account to the interactive user. Repository and queue
paths must be accessible to that active user; granting workspace access to
LocalSystem is neither necessary nor the supported runtime model.

Windows terminates the user-side daemon and its tasks when that user logs off.
Phase 2 must therefore test service stop, user logoff/logon, and reboot behavior
before making any persistence claim. The supported guarantee at this phase is
only independence from the submitting agent application.

Uninstall / rollback:

```powershell
# stop submitting new work, then choose one path for every running task:
pueue wait <id>                   # deliberate drain
# or: pueue kill <id>             # deliberate cancel
# retain: pueue log exports and the queue-state directory
pueued service stop
pueued service uninstall
# delete pinned binaries and queue state only after paths are re-verified
```

Repository launchers are inert checked-in scripts and revert independently.
Do not promise graceful-stop semantics without the Phase 2 empirical check
above.

## Queue policy

```powershell
pueue group add gpu0 -p 1     # training / eval / CUDA validation: serial
pueue group add cpu  -p 2     # analysis / validation / reporting: 2-wide
```

GPU tasks are whole jobs (one seed, eval, or benchmark invocation per task).
The Pueue task ID is the stable operational handle; quote it in
`JOB_STATUS_<node>.md`.

## Procedures

The target machine's Windows PowerShell policy may reject `-File`. The launcher
command therefore uses the explicit process-only `-ExecutionPolicy Bypass`
override. This does not modify user or machine policy; it is acceptable only
because the agent submits a checked-in launcher after verifying the task.

Pueue reconstructs task commands for execution by a shell. Passing the launcher
and JSON as separate `pueue add` arguments loses protective quoting. Submit one
complete launcher command in a stashed task, set the JSON through Pueue's task
environment API, and enqueue only after both operations succeed:

```powershell
# submit (agent side, after payload verification)
$repo = 'D:\CodexShannon\rwkv-rosa-compute'
$launcher = 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass' +
  ' -File "' + $repo + '\scripts\pueue_wrap.ps1"' +
  ' -RepoRoot "' + $repo + '"'
$taskJson = @('python', '-u', 'scripts\some_task.py', '--flag', 'value') |
  ConvertTo-Json -Compress

# The task cannot start before its environment is attached.
$taskId = pueue add --group cpu --stashed --print-task-id $launcher
pueue env set $taskId PUEUE_TASK_JSON $taskJson
pueue enqueue $taskId

# machine-readable state
pueue status --json

# output + exit code history
pueue log <id>

# block until done
pueue wait <id>

# cancel a queued/running task
pueue kill <id>

# Phase 2 persistence test (not a current guarantee): record status/log,
# restart the service, log off/on, and reboot in separate trials; compare
# task state, logs, exit codes, and whether an in-flight process survived.
```

## Environment contract

Pueue owns lifetime, not environments. Every repository owns a launcher; for
this workstation's RWKV checkout that is `scripts/pueue_wrap.ps1`, which
dot-sources `scripts/init_cuda_env.ps1` (venv python, vswhere/vcvars64,
newest-toolset selection, optional `EXP0_REQUIRE_RWKV_CUDA=1`) and executes
its task array verbatim. See the rwkv-rosa-compute repository for both
scripts and the `-SelfCheck` CPU-only validation mode.
