"""Shared-folder publish/claim helpers for the two-agent exchange.

Syncthing transfers each file independently and stages through temp files, so a
payload can be visible while still incomplete. Publishing writes the payload
first and a `<name>.sha256` sidecar second; a consumer treats a payload as ready
only when the sidecar exists AND the hash matches. A mismatch means the transfer
is still in flight - wait and retry, do not consume.

    python sync_tools.py publish <file> [<file> ...]
    python sync_tools.py claim <dir>       # list ready / not-ready
    python sync_tools.py wait <dir>        # block until everything is ready
"""
import hashlib
import sys
import time
from pathlib import Path

TMP_PREFIXES = (".syncthing.", "~syncthing~")
# Syncthing metadata and version history are not payloads.
SKIP_DIRS = (".stfolder", ".stversions", ".stignore")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def publish(paths) -> int:
    for p in paths:
        p = Path(p)
        digest = sha256(p)
        p.with_suffix(p.suffix + ".sha256").write_text(
            f"{digest}  {p.name}\n", encoding="utf-8"
        )
        print(f"published {p.name}  {digest[:16]}...")
    return 0


def _syncing(directory: Path) -> list:
    return [f.name for f in directory.rglob("*")
            if any(f.name.startswith(t) for t in TMP_PREFIXES)
            and not any(part.startswith(".st") for part in f.parts)]


def status(directory: Path):
    """Return (ready, transferring, unverified).

    A hash mismatch means the file is still in flight - wait. A missing sidecar
    means the publisher did not use this protocol, which is not a transfer
    problem and needs a human decision rather than a retry.
    """
    ready, transferring, unverified = [], [], []
    for p in sorted(directory.rglob("*")):
        if not p.is_file() or p.suffix == ".sha256":
            continue
        if any(part in SKIP_DIRS or part.startswith(".st") for part in p.parts):
            continue
        if any(p.name.startswith(t) for t in TMP_PREFIXES):
            continue
        side = p.with_suffix(p.suffix + ".sha256")
        if not side.exists():
            unverified.append(p)
            continue
        want = side.read_text(encoding="utf-8").split()[0]
        if sha256(p) != want:
            transferring.append(p)
        else:
            ready.append(p)
    return ready, transferring, unverified


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd, target = sys.argv[1], sys.argv[2]
    if cmd == "publish":
        return publish(sys.argv[2:])

    directory = Path(target)
    if cmd == "claim":
        ready, transferring, unverified = status(directory)
        inflight = _syncing(directory)
        for p in ready:
            print(f"READY        {p.relative_to(directory)}")
        for p in transferring:
            print(f"TRANSFERRING {p.relative_to(directory)}  (hash mismatch, retry)")
        for p in unverified:
            print(f"UNVERIFIED   {p.relative_to(directory)}  (no sidecar; not published via this protocol)")
        if inflight:
            print(f"syncthing temp files present: {len(inflight)}")
        return 0 if not transferring and not inflight else 1

    if cmd == "wait":
        deadline = time.time() + 3600
        while time.time() < deadline:
            ready, transferring, _unver = status(directory)
            if ready and not transferring and not _syncing(directory):
                print(f"all {len(ready)} file(s) ready")
                return 0
            time.sleep(20)
        print("timed out waiting for a stable state")
        return 1

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
