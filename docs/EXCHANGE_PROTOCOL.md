# Shared-folder exchange protocol

Syncthing transfers each file independently and stages through temp files, so a
payload can be **visible on the far side while still incomplete**. A JSON that
parses is not proof it finished — a truncated file often parses as far as it
goes, or fails in a way that looks like a data problem rather than a transfer
one.

## Publishing

Write the payload, then publish a hash sidecar:

    python sync_tools.py publish <file> [<file> ...]

This writes `<file>.sha256` next to each payload. Always publish the sidecar
**after** the payload is completely written.

## Consuming

Never act on a payload that has no matching sidecar, and never act on one whose
hash does not match:

    python sync_tools.py claim <dir>     # prints READY / PENDING per file
    python sync_tools.py wait <dir>      # blocks until stable, exit 0

Three states, and they need different responses:

- `READY` — sidecar present, hash matches. Safe to consume.
- `TRANSFERRING` — sidecar present, hash does not match. The file is mid-flight.
  Expected and harmless; wait and re-check. Never consume it.
- `UNVERIFIED` — no sidecar. Not a transfer problem: the publisher did not use
  this protocol. Needs a decision, not a retry.

`claim` also reports any `.syncthing.*` / `~syncthing~*` temp files present,
which is a direct signal that a transfer is in progress in that directory.
Syncthing's own `.stfolder` / `.stversions` metadata is excluded.

`claim` exits 0 when nothing is transferring, 1 otherwise, so it can gate a
script directly.

## Conventions

- **Results go in `exp0_0b_seed_study/inbox/`.** Training reports (~62 KB) and
  evaluation JSONs (~1.8 MB) are welcome; please do not sync checkpoints
  (~1.3 GB each) unless asked for a specific one.
- **Leave the reference and challenge files alone.** `challenge/` is the frozen
  instance set and must stay byte-identical on both nodes.
- **Announce long jobs** by dropping a short note in the folder root, so the
  other node does not duplicate work.

## Polling

Both nodes poll roughly every 15 minutes. If something is time-critical, flag it
through the operator rather than relying on the poll.

## Dataset fingerprints

Two different hashes, answering two different questions. Both are needed and
they are not interchangeable.

**Transfer integrity** - the `.sha256` sidecar, over the file bytes. Answers
"did this arrive intact". Changes if anything in the envelope changes.

**Content identity** - `content_sha256`, over the payload's `instances` array
alone. Answers "is this the same data". Survives re-serialisation, metadata
edits and pretty-printing, so two nodes can confirm they audited the same
instances even if the files differ byte-for-byte.

**The serialisation must be pinned or the convention is useless.** Agreeing on
"hash the instances array" is not enough - the same array gives different
digests under different whitespace:

```text
json.dumps(instances, sort_keys=True, separators=(',', ':'))   f443de0a964ff119...
json.dumps(instances, sort_keys=True)                          5708b1b3c89c646a...
```

The canonical form is **compact separators, sorted keys, UTF-8**:

```python
hashlib.sha256(
    json.dumps(instances, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
```

This was found the hard way: one artefact briefly carried four different
identifiers across two nodes - the embedded field computed over the envelope
minus itself, the sidecar over file bytes, and a third value in an audit report.
Quote `content_sha256` in reports; quote the sidecar only when discussing
transfer.
