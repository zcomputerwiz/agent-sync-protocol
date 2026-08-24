#!/usr/bin/env python3
"""Event-driven watcher + wake bridge for the shared sync directory.

Deployed by opencode-dijkstra per D:\\ProjectSync\\WATCHER_SETUP_GUIDE.md
(author: antigravity-ampere). Local modifications:
  - IGNORE_NAMES customized to this node's own published files.
  - Continuous operation: does not exit on first event; keeps scanning until
    the shift timeout so subsequent events wake promptly.
  - Wake bridge: on a detected event, invokes `opencode run` headlessly so a
    fresh agent turn digests the change (debounced, single-flight).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

WATCH_DIR = Path("C:/ProjectSync") if Path("C:/ProjectSync").exists() else Path("D:/ProjectSync")
WORKSPACE = Path("D:/OpenCode")
WAKE_LOG_DIR = WORKSPACE / "wake_runs"
DEBOUNCE_SEC = 300

IGNORE_NAMES = {
    ".stfolder",
    ".stversions",
    ".tmp",
    # --- opencode-dijkstra's own publications (do not self-trigger) ---
    "AGENT_OPENCODE_DIJKSTRA.md",
    "JOB_STATUS_OPENCODE_DIJKSTRA.md",
}

WAKE_PROMPT = (
    "/sync-check Automated watchdog turn (not opencode-dijkstra itself - "
    "label any output 'watchdog', do not sign as dijkstra). Sync-folder "
    "activity detected. Run the sync-check procedure now and produce a "
    "concise digest. If an item is URGENT or addressed to opencode-dijkstra, "
    "say so prominently at the top."
)

WAKE_MODEL = "opencode/nemotron-3-ultra-free"


def is_ignored(path: Path) -> bool:
    for part in path.parts:
        if part in {".stfolder", ".stversions"} or part.endswith(".tmp") or part.startswith("~"):
            return True
    if path.name in IGNORE_NAMES or path.name.endswith(".tmp") or path.name.startswith("~"):
        return True
    return False


def scan_state(root: Path) -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    if not root.exists():
        return state
    try:
        for p in root.rglob("*"):
            if not is_ignored(p) and p.is_file():
                try:
                    st = p.stat()
                    state[str(p)] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    pass
    except OSError:
        pass
    return state


def last_wake_age() -> float:
    marker = WORKSPACE / ".last_wake_ts"
    try:
        return time.time() - float(marker.read_text())
    except (OSError, ValueError):
        return float("inf")


def stamp_wake() -> None:
    try:
        (WORKSPACE / ".last_wake_ts").write_text(str(time.time()))
    except OSError:
        pass


def wake_agent(summary: list[str]) -> None:
    age = last_wake_age()
    if age < DEBOUNCE_SEC:
        print(f"Wake debounced ({age:.0f}s < {DEBOUNCE_SEC}s); "
              f"{len(summary)} changes deferred.", flush=True)
        return
    WAKE_LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = WAKE_LOG_DIR / f"wake_{stamp}.log"
    exe = os.environ.get("OPENCODE_EXE", "opencode")
    try:
        with open(outfile, "w", encoding="utf-8") as fh:
            fh.write("EVENTS:\n" + "\n".join(f"  - {s}" for s in summary) + "\n\n")
            fh.flush()
            subprocess.Popen(
                [exe, "run", "-m", WAKE_MODEL, "--title", "watchdog-sync",
                 WAKE_PROMPT],
                stdout=fh, stderr=subprocess.STDOUT,
                cwd=str(WORKSPACE),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        stamp_wake()
        print(f"Wake dispatched -> {outfile.name}", flush=True)
    except OSError as exc:
        print(f"Wake dispatch failed: {exc}", flush=True)


def main() -> int:
    shift_sec = int(sys.argv[1]) if len(sys.argv) > 1 else 14400
    while True:  # self-restarting shifts; this process is the only writer
        print(f"Monitoring {WATCH_DIR} for incoming agent events "
              f"(shift {shift_sec}s)...", flush=True)
        try:
            run_shift(shift_sec)
        except Exception as exc:  # never die; log and continue
            print(f"Shift crashed: {exc!r}", flush=True)
            time.sleep(5)


def run_shift(shift_sec: int) -> None:
    initial_state = scan_state(WATCH_DIR)
    start_time = time.time()

    while (time.time() - start_time) < shift_sec:
        time.sleep(1.0)
        current_state = scan_state(WATCH_DIR)

        changed = []
        for path_str, (mtime, size) in current_state.items():
            if path_str not in initial_state:
                changed.append(f"CREATED: {Path(path_str)} ({size} bytes)")
            elif initial_state[path_str] != (mtime, size):
                changed.append(f"MODIFIED: {Path(path_str)} ({size} bytes)")
        for path_str in initial_state:
            if path_str not in current_state:
                changed.append(f"DELETED: {Path(path_str)}")

        if changed:
            print("\n" + "=" * 60, flush=True)
            print(f"EVENT DETECTED in {WATCH_DIR}:", flush=True)
            for c in changed:
                print(f"  - {c}", flush=True)
            print("=" * 60, flush=True)

            # Settle period for multi-file transfers
            time.sleep(2.0)
            wake_agent(changed)

            initial_state = current_state  # continuous operation


if __name__ == "__main__":
    raise SystemExit(main())
