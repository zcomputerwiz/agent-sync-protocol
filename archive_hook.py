#!/usr/bin/env python3
"""Per-node archive hook: mirror the shared folder into a local-only git repo.

Optional component of zcomputerwiz/agent-sync-protocol (proposed by
opencode-dijkstra, 2026-08-24). The archive lives OUTSIDE the synced tree -
never place .git inside a Syncthing-managed directory; multi-writer git over
file sync corrupts repositories.

What it gives each node, locally:
  - full version history of every payload/sidecar/manifest ever seen,
    including deletions recorded as deletions
  - per-node receipt times (commit timestamps), diffable snapshots
  - restorability of any byte referenced by a supersession manifest, which
    makes a missing supersedes entry safely informational rather than a gap

Usage:
    python archive_hook.py <source_dir> <archive_dir>

Run repeatedly; each invocation copies changed/new payloads into the archive
tree, applies deletions, and commits when anything changed. stdlib + git.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def ignored(p: Path) -> bool:
    for part in p.parts:
        if part in {".stfolder", ".stversions", "__pycache__"}:
            return True
    n = p.name
    return (n.endswith(".tmp") or n.startswith(".syncthing.")
            or n.startswith("~syncthing~") or n.startswith("~$"))


def scan(source: Path) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for p in source.rglob("*"):
        if p.is_file() and not ignored(p):
            try:
                st = p.stat()
                out[p.relative_to(source).as_posix()] = (st.st_mtime_ns, st.st_size)
            except OSError:
                continue
    return out


def load_state(archive: Path) -> dict:
    f = archive / ".sync_state.json"
    if f.exists():
        try:
            return {k: tuple(v) for k, v in
                    json.loads(f.read_text(encoding="utf-8")).items()}
        except (ValueError, OSError):
            pass
    return {}


def save_state(archive: Path, state: dict) -> None:
    (archive / ".sync_state.json").write_text(
        json.dumps(state), encoding="utf-8")


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args[0]}: {r.stderr.strip()}")
    return r.stdout.strip()


def ensure_repo(archive: Path) -> None:
    archive.mkdir(parents=True, exist_ok=True)
    if not (archive / ".git").exists():
        git(archive, "init")
        git(archive, "config", "user.name", "sync-archive")
        git(archive, "config", "user.email",
            f"{os.environ.get('SYNC_NODE', 'node')}@archive.local")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    source, archive = Path(sys.argv[1]), Path(sys.argv[2])
    if not source.is_dir():
        print(f"source missing: {source}")
        return 2
    ensure_repo(archive)

    state = load_state(archive)
    current = scan(source)
    rel_all = set(current) | set(state)

    added = modified = deleted = copied = 0
    for rel in sorted(rel_all):
        dest = archive / rel
        if rel not in current:                      # deleted at source
            if dest.exists():
                dest.unlink()
                deleted += 1
            continue
        mtime, size = current[rel]
        if state.get(rel) == (mtime, size) and dest.exists():
            continue                                # unchanged
        src_file = source / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp = dest.with_name(dest.name + ".archiving.tmp")
            tmp.write_bytes(src_file.read_bytes())
            tmp.replace(dest)
            copied += 1
            added += 1 if rel not in state else 0
            modified += 0 if rel not in state else 1
        except OSError as exc:
            print(f"skip {rel}: {exc}")

    save_state(archive, current)

    if not (added or modified or deleted):
        print("archive up to date")
        return 0

    git(archive, "add", "-A")
    msg = (f"sync {time.strftime('%Y-%m-%dT%H:%M:%S')} - "
           f"+{added} new, ~{modified} modified, -{deleted} deleted "
           f"({copied} files copied)")
    git(archive, "commit", "-m", msg)
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
