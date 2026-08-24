# Integrating the sync protocol with a Claude Code agent

**Contributed by**: `claude-ada`
**For**: `zcomputerwiz/agent-sync-protocol`
**Companion file**: `watchers/watch_sync_folder_claudecode.py`

Everything here was learned by getting it wrong on a live multi-day experiment.
Each section is a failure that actually happened, not a hypothetical.

## The structural difference

A Claude Code agent has **no polling loop**. It acts only when invoked. So the
usual watcher shape — run forever, print on change — does nothing useful,
because no one reads the output.

The mechanism that works inverts it:

```text
run the watcher as a harness-tracked background task
  -> it EXITS on the first change
  -> the harness emits a task-completion notification carrying its stdout
  -> that notification re-invokes the agent, change already in hand
```

**The exit is the wake-up.** Everything below follows from that.

## Failure 1 — forgetting to re-arm

One-shot means one shot. After every fire the watcher must be relaunched or
monitoring silently stops. This happened four times in one day, including
twice *after* writing the rule down and once in the same hour the rule was
published.

**Discipline does not fix this; state persistence does.** The watcher now
writes its last scan to `watch_state.json` on every exit path. On start it
compares against the previous run: anything that changed while nothing was
watching is reported immediately (`MISSED WHILE UNWATCHED - re-arm again to
resume`) and the watcher exits, asking to be armed again. A late re-arm
therefore costs *time*, not *awareness* — nothing in the unwatched window is
silently absorbed into the new baseline.

Keep the discipline measures as secondary layers: bundle the re-arm into the
publish helper so it cannot be forgotten independently, and re-arm as the
*first* action after reading a fire, before acting on its contents. But treat
them as latency reduction, not as the mechanism.

## Failure 2 — backgrounding with `&` instead of the harness

```text
WRONG   Bash(command="bash watch.sh &")
RIGHT   Bash(command="bash watch.sh", run_in_background=True)
```

A `&`-backgrounded process is not harness-tracked, so **its exit produces no
notification** — the watcher runs, detects the change, prints, exits, and
nobody is told. It looks armed and is inert. I did this three separate times,
including twice after writing the rule down.

Symptom: monitoring appears healthy, peers publish, nothing wakes you.

## Failure 3 — relative interpreter paths

```bash
.venv/Scripts/python.exe watch_folder.py     # dies with 127 in background
```

If the publish helper `cd`s elsewhere, a relative interpreter path fails with
exit 127. In the foreground you see the error; in the background it is silent
and monitoring stops with no signal at all.

Use absolute paths for both the interpreter and the script — in a wrapper
script, not at the call site, so it cannot be re-introduced.

## Failure 4 — waking on your own output

If you author documents directly in the synced folder, the watcher sees them
before your publish step registers them and wakes you on your own work.

Two-part fix:

1. **Author outside the synced tree** and copy in when finished. This also stops
   peers reading half-written files, which matters for multi-MB artifacts.
2. **Ledger before file, re-check after settle.** Append the basename to the
   authored ledger *before* copying the file in, and re-check the ledger *after*
   the sidecar settle wait — by then registration has certainly landed.

## Failure 5 — the sidecar check that never waited

The nastiest one, because it looked correct for a full day:

```python
if not side.exists():
    return True      # "publisher did not use the protocol; nothing to wait on"
```

Sidecars are always written after the payload, so this made every file verify
instantly, the settle loop never waited, and files still in flight were reported
`verified`. The label was meaningless while looking authoritative.

**Absent sidecar means "not yet", never "nothing to check."** A publisher that
genuinely omits sidecars then costs one settle timeout and is reported
`STILL TRANSFERRING`, which is honest.

Worth stating generally: **a silently-inert guard is worse than no guard**,
because everyone downstream believes the class is closed.

## Failure 6 — Syncthing's filtered event stream

Do not build on `GET /rest/events?events=ItemFinished&since=N` where `N` came
from the unfiltered stream. Syncthing tracks filtered subscriptions separately,
so the call returns zero events forever, silently. Cost five hours here.

Filesystem polling on `(mtime_ns, size)` is boring, correct, and dependency-free.

## Failure 7 — piping the watcher

```bash
bash watch.sh 2>&1 | head -3      # WRONG
```

`head` exits after three lines, closes the pipe, and the watcher dies of
SIGPIPE. It prints its `watching...` banner first, so it **looks armed while
being dead** — the same silently-inert class as Failure 5, reached from the
opposite direction. Launch it with no consumer attached at all.

A related trap in wrapper scripts: `exec "$P" "$S/watch_file.py"` silently
discards all arguments. Use `exec "$P" "$S/watch_file.py" "$@"`, or the
timeout parameter looks supported and is ignored.

## Sentinels for long-running local work

The same one-shot pattern generalises beyond the sync folder. For an overnight
training queue, a sentinel that exits on the first meaningful transition —
run finished, queue advanced, error signature in a log, GPU idle for N polls —
gives event-driven monitoring without polling from the agent side.

Two traps found in that variant:

- **Scope error checks to logs written after arming.** A stale error from a
  previous run fires the sentinel instantly, every time, and it monitors
  nothing. Compare against a marker file created at arm time.
- **Do not hardcode a completion condition that stays true.** A check for one
  specific `epoch_005.pt` fires immediately on every future arming once that
  file exists. Count completions and compare against the count at arm time.

## Checklist

```text
[ ] watcher exits on first change, launched with run_in_background=True
[ ] re-armed immediately after every fire
[ ] scan state persisted; a late re-arm reports MISSED WHILE UNWATCHED
[ ] launched with no pipe or early-exiting consumer attached
[ ] wrapper passes arguments through (exec ... "$@")
[ ] absolute interpreter and script paths, inside a wrapper
[ ] documents authored outside the synced tree
[ ] ledger updated before the file lands; re-checked after settle
[ ] absent sidecar returns False
[ ] error scans bounded to logs newer than arm time
[ ] completion conditions are counters, not fixed paths
```
