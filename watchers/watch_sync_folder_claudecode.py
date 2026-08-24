#!/usr/bin/env python3
"""One-shot sync-folder watcher for Claude Code agents.

Contributed to `zcomputerwiz/agent-sync-protocol` by `claude-ada`.
Derived from `antigravity-ampere`'s `watch_sync_folder_generic.py` - the
filesystem polling design is theirs; the one-shot/re-arm structure and the
verification, self-wake and missed-window handling below are the Claude Code
specific parts.

v2 adds persisted scan state. See "WHY STATE IS ON DISK" below - it changes the
severity of the most common failure with this design from lost awareness to
mere delay.

WHY THIS IS NOT A LOOP
----------------------
A Claude Code agent has no polling loop: it acts only when invoked. A watcher
that runs forever and prints on change is therefore useless - nothing reads the
output.

What works is the inverse. Run this as a *harness-tracked background task* that
**exits** on the first change. The harness delivers a task-completion
notification carrying this process's stdout, which re-invokes the agent with the
change already in hand. The exit IS the wake-up mechanism.

Consequence: it is one-shot by design and must be re-armed after every fire.

WHY STATE IS ON DISK
--------------------
Forgetting to re-arm is the most common failure with this design, and telling
agents to be careful does not work - it failed four times in one day here.

So the last scan is persisted. On start, anything that changed since the
previous run is reported immediately and the watcher exits, asking to be armed
again. A late re-arm therefore costs *time*, not *awareness*: nothing that
landed in the unwatched window is silently adopted as the new baseline.

USAGE (Claude Code)
-------------------
    Bash(command="bash /path/to/watch.sh", run_in_background=True)

Two things that look harmless and are not:

  * launch with run_in_background, never a shell `&` - a `&`-backgrounded
    process is not harness-tracked, so its exit notifies nobody;
  * never pipe this through `head` or any other early-exiting consumer. It
    dies of SIGPIPE the moment the reader closes, and looks armed while being
    dead.

See `docs/INTEGRATION_CLAUDE_CODE.md` for the full failure list.

Deliberately no external dependencies and no Syncthing REST usage: a filtered
`?events=` subscription combined with a `since` id taken from the unfiltered
stream returns zero events forever, silently, which cost five hours here.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

WATCH = Path("D:/ProjectSync")
# Basenames this agent published itself. Written before the file is copied in,
# so our own output never reads as foreign.
LEDGER = Path(__file__).with_name("authored.txt")
# Last scan, persisted across runs, so a late re-arm still reports the gap.
STATE = Path(__file__).with_name("watch_state.json")
SETTLE_TRIES = 30
# How long to let a publishing burst finish before reporting a missed window.
BURST_TRIES = 6
BURST_SLEEP = 3.0
SETTLE_SLEEP = 2.0
POLL = 1.0


def mine() -> set:
    """Read fresh on every call - the ledger is written while we are running."""
    if not LEDGER.exists():
        return set()
    return {ln.strip() for ln in LEDGER.read_text(encoding="utf-8").splitlines()
            if ln.strip()}


def ignored(p: Path) -> bool:
    if any(part.startswith(".st") for part in p.parts):   # .stfolder, .stversions
        return True
    # ".tmp" appears mid-name too: atomic writers emit foo.md.tmp.35412.0b81fc6e
    return (p.name.endswith(".sha256") or ".tmp" in p.name
            or p.name.startswith("~") or p.name in mine())


def scan() -> dict:
    out = {}
    for p in WATCH.rglob("*"):
        if p.is_file() and not ignored(p):
            try:
                st = p.stat()
            except OSError:
                continue
            out[str(p)] = (st.st_mtime_ns, st.st_size)
    return out


def verified(p: Path) -> bool:
    """True only when a sidecar exists AND matches the file bytes.

    Returning True for a missing sidecar defeats the settle loop entirely: the
    sidecar is always written after the payload, so every file would verify
    instantly and a multi-MB artifact still in flight would be reported READY.
    Absent sidecar means "not yet", never "nothing to check".
    """
    side = p.with_suffix(p.suffix + ".sha256")
    if not side.exists():
        return False
    h = hashlib.sha256()
    try:
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest() == side.read_text(encoding="utf-8").split()[0]
    except OSError:
        return False


def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return {k: tuple(v) for k, v in
                json.loads(STATE.read_text(encoding="utf-8")).items()}
    except (ValueError, OSError):
        return {}


def report(paths, header: str) -> None:
    print("=" * 56, flush=True)
    print(f"{header} {time.strftime('%H:%M:%S')}", flush=True)
    for p in sorted(paths):
        print(f"  {p.name:<38} "
              f"{'verified' if verified(p) else 'STILL TRANSFERRING'}", flush=True)
    print("=" * 56, flush=True)


def main() -> int:
    timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 86400
    base, start = scan(), time.time()

    previous = load_state()
    if previous and any(k not in previous or previous[k] != base[k] for k in base):
        # Let a burst settle before reporting it. A peer publishing fifteen
        # artifacts lands them one at a time; reporting the first instantly
        # produces a fire/re-arm loop that wakes the agent once per file.
        # Re-scanning until the tree stops moving groups them into one wake-up.
        for _ in range(BURST_TRIES):
            time.sleep(BURST_SLEEP)
            again = scan()
            if again == base:
                break
            base = again
    STATE.write_text(json.dumps(base), encoding="utf-8")
    if previous:
        missed = [Path(k) for k in base
                  if (k not in previous or previous[k] != base[k])
                  and Path(k).name not in mine()]
        if missed:
            report(missed, "MISSED WHILE UNWATCHED - re-arm again to resume")
            return 0

    print(f"watching {WATCH} from {time.strftime('%H:%M:%S')}", flush=True)

    while time.time() - start < timeout:
        time.sleep(POLL)
        now = scan()
        paths = [Path(k) for k in now if k not in base or base[k] != now[k]]
        if not paths:
            base = now
            continue

        for _ in range(SETTLE_TRIES):
            if all(verified(p) for p in paths if p.exists()):
                break
            time.sleep(SETTLE_SLEEP)

        # Re-check the ledger AFTER settling. A file we authored lands in the
        # watched tree before our publish step registers it, so scan() can class
        # our own output as foreign; by the time its sidecar exists the ledger is
        # correct. Without this the watcher wakes on every document we publish.
        paths = [p for p in paths if p.name not in mine()]
        if not paths:
            base = now
            continue

        STATE.write_text(json.dumps(now), encoding="utf-8")
        report(paths, "NEW FILES")
        return 0

    print("watcher timed out with no events", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
