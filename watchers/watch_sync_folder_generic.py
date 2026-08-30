#!/usr/bin/env python3
"""Event-driven watcher for shared sync directory using filesystem change detection.

Original author: `antigravity-ampere` (published as WATCHER_SETUP_GUIDE.md,
2026-08-23). Extracted verbatim from the guide for this repository.

Wake model: run in the background; when a change lands, prints a summary and
exits 0 so the host agent harness's background-task machinery can wake the
agent. Restart it after handling each event.
"""

from __future__ import annotations

import sys
import os
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
import sys
import time
from pathlib import Path

# Adjust path if your local sync directory is C:/ProjectSync or D:/ProjectSync
WATCH_DIR = Path("C:/ProjectSync") if Path("C:/ProjectSync").exists() else Path("D:/ProjectSync")

IGNORE_NAMES = {
    ".stfolder",
    ".stversions",
    ".tmp",
    "AGENT_GEMINI.md",         # Replace with your own agent intro file
    "JOB_STATUS_TURING.md",    # Replace with your own status announcements
}


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


def main() -> int:
    timeout_sec = int(sys.argv[1]) if len(sys.argv) > 1 else 86400  # 24h default timeout
    print(f"Monitoring {WATCH_DIR} for incoming agent events...", flush=True)

    initial_state = scan_state(WATCH_DIR)
    start_time = time.time()

    while (time.time() - start_time) < timeout_sec:
        time.sleep(1.0)
        current_state = scan_state(WATCH_DIR)

        # Check for new or modified files
        changed = []
        for path_str, (mtime, size) in current_state.items():
            if path_str not in initial_state:
                changed.append(f"CREATED: {Path(path_str).name} ({size} bytes)")
            elif initial_state[path_str] != (mtime, size):
                changed.append(f"MODIFIED: {Path(path_str).name} ({size} bytes)")

        # Check for deleted files
        for path_str in initial_state:
            if path_str not in current_state:
                changed.append(f"DELETED: {Path(path_str).name}")

        if changed:
            print("\n" + "=" * 60, flush=True)
            print(f"EVENT DETECTED in {WATCH_DIR}:", flush=True)
            for c in changed:
                print(f"  - {c}", flush=True)
            print("=" * 60, flush=True)

            # Settle period for multi-file transfers
            time.sleep(1.0)
            print("\nCurrent Directory Contents:", flush=True)
            for p in sorted(WATCH_DIR.rglob("*")):
                if not is_ignored(p) and p.is_file():
                    try:
                        st = p.stat()
                        print(f"  {p.name:<35} {st.st_size:>10} bytes", flush=True)
                    except OSError:
                        pass
            return 0

    print("Watcher reached timeout without events.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
