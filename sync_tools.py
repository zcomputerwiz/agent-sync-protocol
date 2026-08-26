"""Shared-folder publish/claim helpers for the two-agent exchange.

Syncthing transfers each file independently and stages through temp files, so a
payload can be visible while still incomplete. Publishing writes the payload
first and a `<name>.sha256` sidecar second; a consumer treats a payload as ready
only when the sidecar exists AND the hash matches. A mismatch means the transfer
is still in flight - wait and retry, do not consume.

    python sync_tools.py publish <file> [<file> ...]
    python sync_tools.py claim <dir>       # list ready / not-ready
    python sync_tools.py wait <dir>        # block until everything is ready
    python sync_tools.py resolve <dir>     # supersession manifest resolution

`resolve` implements the R1-R7 supersession-manifest protocol (Class C,
ratified in VERIFIED_SUPERSESSION_MANIFEST_CLASS_C.md): read-only, stdlib,
deterministic, fail-closed on CONFLICT / CYCLE / BROKEN_REF, transitive
across replacement chains, authority-scoped per R7 (a manifest applies only
to artifacts published by the same node), with R6's existence asymmetry
(absent supersedes targets are informational; absent or mismatched
replacement is a failure).
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path

TMP_PREFIXES = (".syncthing.", "~syncthing~")
# Syncthing metadata and version history are not payloads.
SKIP_DIRS = (".stfolder", ".stversions", ".stignore")

HEX64 = re.compile(r"[0-9a-f]{64}")


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


# ---------------------------------------------------------------------------
# Supersession manifests (R1-R7). Read-only; never mutates artifacts.
# ---------------------------------------------------------------------------

def _node_key(path: str, sha: str) -> str:
    return f"{path}#{sha}"


def _payload_state(all_index: dict[str, Path], state_map: dict[str, str],
                   rel: str, expected_sha: str) -> tuple[str, str | None]:
    """Exact-case reference check. Returns (state, actual_digest|None).

    states: 'READY' (bytes hash-verified) | 'NONREADY' | 'ABSENT'
    Exact string keys defeat case-insensitive filesystem matching (R2).
    """
    if rel not in all_index:
        return "ABSENT", None
    st = state_map.get(rel)
    if st != "READY":
        return "NONREADY", None
    h = hashlib.sha256()
    with open(all_index[rel], "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    return ("READY", digest) if digest == expected_sha else ("MISMATCH", digest)


def _canonical_rel_path(raw: str) -> str | None:
    """Return canonical root-relative posix path, or None if invalid (R2).

    Rejects: absolute paths, drive prefixes, backslashes, leading/trailing
    slashes, '.' or '..' segments, empty segments, non-NFC unicode.
    """
    import unicodedata
    if not isinstance(raw, str) or not raw:
        return None
    if unicodedata.normalize("NFC", raw) != raw:
        return None
    if "\\" in raw or raw.startswith("/") or raw.endswith("/"):
        return None
    if re.match(r"^[A-Za-z]:", raw):
        return None
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return "/".join(parts)


def _rfc3339(value) -> bool:
    """Shape check plus real calendar validation via datetime.fromisoformat."""
    if not isinstance(value, str):
        return False
    if not re.match(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}"
                    r"(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$", value):
        return False
    try:
        from datetime import datetime
        datetime.fromisoformat(
            value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return False
    return True


def resolve_dir(directory: Path) -> dict:
    """Resolve supersession manifests deterministically. See module docstring."""
    result = {
        "artifacts": {},        # node_key -> {"status": str, "by": key|None}
        "requested": [],        # non-authoritative manifests awaiting action
        "exceptions": [],       # CONFLICT / CYCLE / BROKEN_REF / INVALID_MANIFEST
        "manifests": [],        # metadata for every manifest considered
        "informational": [],    # absent supersedes targets (R6)
        "skipped_not_ready": [],
    }

    edges = []                  # (src_key, tgt_key|None, manifest_ref)
    all_nodes = set()           # every referenced-and-verified node

    ready, transferring, unverified = status(directory)
    all_index: dict[str, Path] = {}
    state_map: dict[str, str] = {}
    for st_val, plist in (("READY", ready), ("TRANSFERRING", transferring),
                          ("UNVERIFIED", unverified)):
        for p in plist:
            rel = p.relative_to(directory).as_posix()
            all_index[rel] = p
            state_map[rel] = st_val
    for rel in sorted(
            [p.relative_to(directory).as_posix() for p in transferring]
            + [p.relative_to(directory).as_posix() for p in unverified]):
        if rel.lower().endswith(".json"):
            result["skipped_not_ready"].append(rel)

    # Only READY CLOSED_*.json files are manifest candidates (P1 fix: a
    # non-READY closure must be skipped, never parsed and applied).
    manifest_index = {rel: p for rel, p in all_index.items()
                      if state_map[rel] == "READY"
                      and Path(rel).name.startswith("CLOSED_")
                      and rel.lower().endswith(".json")}

    for rel in sorted(manifest_index):
        path = manifest_index[rel]
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            result["exceptions"].append(
                {"kind": "INVALID_MANIFEST", "manifest": rel,
                 "detail": f"unreadable: {exc}"})
            continue
        bad = None
        if not isinstance(m, dict):
            bad = "not an object"
        elif m.get("schema_version") != 1:
            bad = f"schema_version {m.get('schema_version')!r} != 1"
        elif m.get("status") != "superseded":
            bad = f"status {m.get('status')!r} != 'superseded'"
        elif not isinstance(m.get("from"), str) or not m["from"]:
            bad = "missing 'from'"
        elif not _rfc3339(m.get("date", "")):
            bad = "missing or malformed 'date' (RFC3339)"
        elif not isinstance(m.get("reason"), str) or not m["reason"].strip():
            bad = "missing 'reason'"
        sup = m.get("supersedes")
        if bad is None and (
                not isinstance(sup, list) or not sup
                or not all(isinstance(e, dict) for e in sup)):
            bad = "'supersedes' must be a non-empty list of objects"
        repl = m.get("replacement")
        if bad is None and repl is not None:
            if not isinstance(repl, dict):
                bad = "invalid 'replacement'"
        if bad is not None:
            result["exceptions"].append(
                {"kind": "INVALID_MANIFEST", "manifest": rel, "detail": bad})
            continue

        # R2: canonical path rules - enforced before any filesystem access.
        cand_paths = [e.get("path") for e in sup]
        if repl is not None:
            cand_paths.append(repl.get("path"))
        for cp in cand_paths:
            canon = _canonical_rel_path(cp)
            if canon is None:
                bad = f"non-canonical path: {cp!r}"
                break
        if bad is not None:
            result["exceptions"].append(
                {"kind": "INVALID_MANIFEST", "manifest": rel, "detail": bad})
            continue

        entries = []
        publisher_mismatch = False
        for e in sup:
            pub = e.get("publisher")
            # R7: publisher is REQUIRED on every entry and must be a
            # nonempty string. Absent/garbage publisher -> INVALID_MANIFEST.
            if not isinstance(pub, str) or not pub.strip():
                bad = "supersedes entry missing nonempty 'publisher'"
                break
            sha = e.get("sha256")
            if not isinstance(sha, str) or not HEX64.fullmatch(sha):
                bad = f"supersedes entry bad sha256: {sha!r}"
                break
            entries.append({
                "path": e["path"], "sha256": sha, "publisher": pub,
            })
            if pub != m["from"]:
                publisher_mismatch = True
        if bad is None and repl is not None:
            rsha = repl.get("sha256")
            if not isinstance(rsha, str) or not HEX64.fullmatch(rsha):
                bad = f"replacement bad sha256: {rsha!r}"
        if bad is not None:
            result["exceptions"].append(
                {"kind": "INVALID_MANIFEST", "manifest": rel, "detail": bad})
            continue

        # R7 provenance: only the operator may ratify a cross-node manifest.
        # A non-operator author's boolean is inert.
        operator_ratified = (m.get("operator_ratified") is True
                             and m["from"] == "operator")
        authority = ("AUTHORITATIVE" if not publisher_mismatch
                     else "OPERATOR_RATIFIED" if operator_ratified
                     else "REQUESTED")
        meta = {"manifest": rel, "from": m["from"], "date": m["date"],
                "authority": authority,
                "reason": m["reason"].strip(),
                "entries": entries,
                "replacement": repl}
        result["manifests"].append(meta)

        src_keys, tgt_key = [], None

        if authority == "REQUESTED":
            result["requested"].append(meta)
            continue

        # Disk verification (exact-case, READY-gated) applies only to
        # applicable manifests.
        for e in entries:
            key = _node_key(e["path"], e["sha256"])
            src_keys.append(key)
            st_val, _dg = _payload_state(
                all_index, state_map, e["path"], e["sha256"])
            if st_val == "READY":
                all_nodes.add(key)
            elif st_val == "MISMATCH":
                result["exceptions"].append(
                    {"kind": "BROKEN_REF", "manifest": rel,
                     "detail": f"supersedes target bytes mismatch: {key}"})
            elif st_val == "NONREADY":
                result["exceptions"].append(
                    {"kind": "BROKEN_REF", "manifest": rel,
                     "detail": f"supersedes target present but not READY: {key}"})
            elif st_val == "ABSENT":
                result["informational"].append(
                    {"manifest": rel, "detail": f"supersedes target absent: {key}"})
        if repl is not None:
            tgt_key = _node_key(repl["path"], repl["sha256"])
            st_val, _dg = _payload_state(
                all_index, state_map, repl["path"], repl["sha256"])
            if st_val == "READY":
                all_nodes.add(tgt_key)
            else:
                reason = {"MISMATCH": "bytes mismatch",
                          "NONREADY": "present but not READY",
                          "ABSENT": "absent"}[st_val]
                result["exceptions"].append(
                    {"kind": "BROKEN_REF", "manifest": rel,
                     "detail": f"replacement {reason}: {tgt_key}"})

        for sk in src_keys:
            edges.append((sk, tgt_key))

    # Deterministic conflict detection over authoritative edges.
    by_src: dict[str, set] = {}
    for sk, tk in edges:
        by_src.setdefault(sk, set()).add(tk)
    for sk, tgts in sorted(by_src.items()):
        real = {t for t in tgts if t is not None}
        if len(real) > 1:
            result["exceptions"].append(
                {"kind": "CONFLICT", "manifest": "-",
                 "detail": f"{sk} superseded by multiple replacements: "
                           + ", ".join(sorted(real))})

    # Fail-closed: any exception means NOTHING is selected.
    if result["exceptions"]:
        result["artifacts"] = {}
        return result

    # Withdrawal edges (replacement null) conflict with replacement edges
    # for the same source; withdrawals themselves resolve to WITHDRAWN.
    withdrawal_srcs = {sk for sk, tk in edges if tk is None}
    replace_srcs = {sk for sk, tk in edges if tk is not None}
    for sk in sorted(withdrawal_srcs & replace_srcs):
        result["exceptions"].append(
            {"kind": "CONFLICT", "manifest": "-",
             "detail": f"{sk} has both a withdrawal and a replacement"})

    # Transitive resolution over replacement edges only.
    nxt = {}
    for sk, tk in edges:
        if tk is not None and sk not in nxt:
            nxt[sk] = tk

    resolved: dict[str, dict] = {}
    cycle_nodes: set[str] = set()

    def terminal(key: str) -> tuple[str, str | None]:
        seen = set()
        cur = key
        while cur in nxt:
            if cur in seen:
                return "CYCLE", cur
            seen.add(cur)
            cur = nxt[cur]
        return "ACTIVE", cur

    for sk in sorted(replace_srcs):
        st, end = terminal(sk)
        if st == "CYCLE":
            result["exceptions"].append(
                {"kind": "CYCLE", "manifest": "-",
                 "detail": f"cycle at {sk} -> ... -> {end}"})
            cycle_nodes.add(sk)
            continue
        resolved[sk] = {"status": "SUPERSEDED", "by": end}
    for sk in sorted(withdrawal_srcs - replace_srcs):
        resolved[sk] = {"status": "WITHDRAWN", "by": None}
    for key in sorted(all_nodes - set(resolved) - cycle_nodes):
        resolved[key] = {"status": "ACTIVE", "by": None}

    # Second fail-closed gate: cycle resolution may add exceptions.
    if result["exceptions"]:
        result["artifacts"] = {}
    else:
        result["artifacts"] = resolved

    return result


def print_resolve(result: dict) -> int:
    exceptions = result["exceptions"]
    for exc in exceptions:
        print(f"{exc['kind']:<18} [{exc['manifest']}] {exc['detail']}")
    if result["requested"]:
        print("REQUESTED (non-authoritative, not applied):")
        for mm in result["requested"]:
            print(f"  {mm['manifest']}  from={mm['from']}")
    if result["informational"]:
        print("INFORMATIONAL (absent supersedes targets, R6):")
        for info in result["informational"]:
            print(f"  {info['detail']}")
    if result["skipped_not_ready"]:
        print("SKIPPED (not READY):")
        for s in result["skipped_not_ready"]:
            print(f"  {s}")
    print("ARTIFACTS:")
    for key in sorted(result["artifacts"]):
        a = result["artifacts"][key]
        by = f" by {a['by']}" if a["by"] else ""
        print(f"  {a['status']:<10} {key}{by}")
    if not result["artifacts"] and not exceptions:
        print("  none")
    return 2 if exceptions else 0


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

    if cmd == "resolve":
        result = resolve_dir(directory)
        return print_resolve(result)

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
