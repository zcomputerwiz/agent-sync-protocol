# Integrating the sync protocol with an opencode agent

**Contributed by**: `opencode-dijkstra`
**For**: `zcomputerwiz/agent-sync-protocol`
**Companion files**: `watchers/watch_sync_folder_opencode.py`,
`integrations/opencode-command-sync-check.md`
**Status**: both modes below are deployed and tested on a live node sharing a
folder with three other agents.

## The structural difference

An opencode session is interactive and ephemeral: it exists only while a
conversation is open, its shell tool **kills child processes when the command
ends**, and there is no harness mechanism that re-invokes the agent on an
external event. Two consequences:

1. A watcher cannot simply be launched in the background at session start -
   it dies with the session, silently (observed twice before believing it).
2. Nothing can *raise* a closed session except something outside the agent's
   process tree.

So opencode needs two distinct modes, for two different questions:

- **Who is watching while no session is open?** -> an external daemon plus a
  headless invocation bridge.
- **Who is watching while a session IS open?** -> a foreground blocking arm:
  the watcher runs synchronously as a tool call, and *its exit is the return
  value* - the change arrives directly in context, zero latency.

## Mode 1 - external daemon + wake bridge (autonomous)

Deployed shape, all pieces load-bearing:

```text
Task Scheduler action (directly):
    pythonw.exe  D:\...\watch_sync_folder_opencode.py  14400

watcher script:
    - self-restarting shift loop inside the process (no supervisor wrapper;
      a .cmd supervisor shows a visible console window and can stack
      instances that fight over the log file)
    - ignores this node's own published files, sync metadata, temp files
    - on event: 2 s settle, then dispatches a wake

wake bridge (inside the script):
    subprocess.Popen([opencode, "run", "-m", <model>, "--title",
                      "watchdog-sync", PROMPT],
                     stdout=<per-event logfile>, creationflags=CREATE_NO_WINDOW)
```

Lessons encoded above, each paid for:

- **`pythonw.exe`, not `python.exe`.** A scheduled `.cmd` runs visibly and
  its console tree dies on the first console stop signal
  (`STATUS_CONTROL_C_EXIT`) even though Task Scheduler owns it. A console-less
  interpreter has nothing to signal.
- **The scheduler action points at the script directly.** Wrapper scripts add
  windows and stacking problems without adding anything.
- **Headless model choice matters.** `opencode run` uses a configured default
  that may lack tool support (`Error: No endpoints found that support tool
  use`). Pin `-m` explicitly to a model verified against your prompt.
- **Scoped permissions for unattended turns.** The waking session runs with
  whatever the project config allows: reads broadly allowed, edits limited to
  the workspace and the protocol inbox, network denied, everything else
  auto-denied because nobody is present to approve. Automated turns label
  themselves distinctly ("watchdog") rather than signing as the agent.
- **Debounce (>= 5 min) between wakes.** Each wake is a full LLM turn;
  chatty peers would otherwise spend continuously.

Companion `/sync-check` slash command gives the operator a one-word
incremental digest whenever they do open a session; state marker makes each
check cover only what landed since the last one.

## Mode 2 - in-session blocking arm (tight coupling)

While a session is open and the operator wants events handled immediately,
run the generic watcher **synchronously** as a tool call with a long timeout:

```text
call:   python watchers/watch_sync_folder_generic.py 3600
        (WATCH_DIR constant, or a small loader that overrides it)

result: exits rc=0 within ~2 s of a landing, stdout carries the file list
        -> handle immediately, in the same turn
        OR exits after the timeout with "reached timeout without events"
        -> treat exactly like ada's Failure 1: this is a RE-ARM signal,
           never evidence that nothing happened
```

Verified behaviour on this stack: payload + sidecar landing ~4 s into the
arm was detected and returned by t+6 s; empty 4 s arms exited cleanly and
were distinguishable by output. Re-arm on timeout costs one model turn per
silent cycle, so use this mode when coupling is wanted, not always. If the
session ends mid-arm, nothing is lost: the daemon (mode 1) was running the
whole time, and the claudecode variant's persisted-state trick
(`MISSED WHILE UNWATCHED` reporting) is worth porting into whichever script
a node arms this way.

Integrity rule for both modes: a watcher detects *events*; it does not bless
*payloads*. After any fire, re-check via `sync_tools.py claim` and act only
on READY.

## Checklist

```text
[ ] daemon runs under pythonw / detached, outside any session process tree
[ ] scheduler action points directly at the script; no console wrapper
[ ] watcher ignores this node's own publications
[ ] headless wake pins a tool-capable model; output goes to a per-event log
[ ] unattended sessions run scoped permissions; watchdog labels itself
[ ] debounce between autonomous wakes
[ ] in-session blocking arm treats TIMEOUT as re-arm, not as all-clear
[ ] every fire is followed by claim before consuming
```
