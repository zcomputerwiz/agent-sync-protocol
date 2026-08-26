# Machine dispatcher: Pueue on Windows

Status: Phase 1 (documentation + launchers) implemented; service activation is
Phase 2 and waits for the current GPU runner. Ratification: see
`PROPOSAL_PUEUE_MACHINE_TASK_DISPATCHER_SHANNON.md` and the task thread.

## Purpose

A persistent machine-local queue separates submitted jobs from interactive
agent applications. When an agent application dies mid-run (the MSIX
termination incident of 2026-08-25), a queued job keeps running under the
daemon's process tree, with durable queue state, retained logs, and exit
codes. The shared folder remains the cross-machine control plane; Pueue is
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
pueued service status        # if present in the pinned build; else sc query
pueued service stop
pueued service uninstall
```

Phase 2 must empirically verify stop semantics (whether in-flight tasks
drain or are killed on `service stop`) before relying on either behavior,
and verify restart persistence of queue state, logs, and exit codes.

Service identity assumption: run as the interactive user account that owns
`D:\` workspaces and the queue-data directory (LocalSystem would need
explicit ACL grants). Confirm read/write scope covers ONLY the required
workspaces and the queue-data directory before starting real jobs.

Uninstall / rollback:

```powershell
pueue pause --all                 # or per group; let tasks drain
pueue kill <id>                   # deliberate cancel if needed
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

```powershell
# submit (agent side, after payload verification)
pueue add --group cpu -- powershell -NoProfile -File `
  D:\OpenCode\rwkv-rosa-compute\scripts\pueue_wrap.ps1 `
  -RepoRoot D:\OpenCode\rwkv-rosa-compute `
  -ArgsJson '["python","-u","scripts\\some_task.py","--flag","value"]'

# machine-readable state
pueue status --json

# output + exit code history
pueue log <id>

# block until done
pueue wait <id>

# cancel a queued/running task
pueue kill <id>

# restart persistence
# queue state lives in the daemon's data directory; stopping and starting
# the service retains finished-task records, logs, and exit codes. Verify
# once in Phase 2: submit, reboot or restart service, confirm `status --json`
# and `log` unchanged.
```

## Environment contract

Pueue owns lifetime, not environments. Every repository owns a launcher; for
this workstation's RWKV checkout that is `scripts/pueue_wrap.ps1`, which
dot-sources `scripts/init_cuda_env.ps1` (venv python, vswhere/vcvars64,
newest-toolset selection, optional `EXP0_REQUIRE_RWKV_CUDA=1`) and executes
its task array verbatim. See the rwkv-rosa-compute repository for both
scripts and the `-SelfCheck` CPU-only validation mode.
