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

## Release source and version pinning (Phase 2 preflight)

1. Official source only: `https://github.com/Nukesor/pueue/releases`
   (asset `pueue-win-x86_64-<version>.zip` naming per release).
2. Pin by tag. Record in this file, in an ops note, before extraction:

   ```text
   pinned tag        : <e.g. v4.x.y>
   archive sha256    : <computed locally over the downloaded zip>
   download date/url : <...>
   ```

3. Verify: `Get-FileHash <zip> -Algorithm SHA256` must equal the recorded
   value. Upstream may publish checksum assets; if present, require BOTH to
   agree. If they disagree, stop and escalate to the operator.
4. Record the pinned build's `pueued --help` output alongside the record;
   service-management flags are verified against the pinned build, not
   assumed from documentation.

## Service installation (Phase 2)

Native service support varies by release; the pinned build's help output is
authoritative. Two accepted patterns, in order of preference:

```powershell
# A. If the pinned build ships native service management:
pueued --help                      # confirm the service subcommand exists
pueued <native-install-command>

# B. Generic Windows service wrapper (works for any console daemon):
sc.exe create pueued binPath= "\"<installDir>\pueued.exe\" --config \"<configDir>\"" ^
    start= auto DisplayName= "Pueue task queue daemon"
sc.exe description pueued "Machine-local persistent task queue (agent-sync-protocol)"
```

Status / start / stop:

```powershell
sc.exe query pueued
sc.exe start pueued
sc.exe stop pueued          # graceful: in-flight tasks finish first
```

Service identity assumption: run as the interactive user account that owns
`D:\` workspaces and the queue-data directory (LocalSystem would need
explicit ACL grants). Confirm read/write scope covers ONLY the required
workspaces and the queue-data directory before starting real jobs.

Uninstall / rollback:

```powershell
pueue pause --all                 # or per group; let tasks drain
pueue kill <id>                   # deliberate cancel if needed
# retain: pueue log exports and the queue-state directory
sc.exe stop pueued
sc.exe delete pueued
# delete pinned binaries and queue state only after paths are re-verified
```

Repository launchers are inert checked-in scripts and revert independently.

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
