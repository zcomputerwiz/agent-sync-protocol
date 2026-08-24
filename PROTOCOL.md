# Protocol rules (normative)

Version: 0.1 · Status: in force on the founding fleet · Provenance notes inline.

The scope is one shared folder ("the folder") synced between member machines
by any file-replication mechanism. Everything here exists because an incident
happened without it; the originating incidents are summarized in §9.

## 1. Folder layout

- `.stfolder/`, `.stversions/`, `.stignore` are sync-engine metadata. Never
  read them as payloads; watchers and `sync_tools.py` skip them.
- Payloads live at the root or under project subdirectories
  (`<project>/inbox/` for results). One project per subdirectory.
- Reference/frozen datasets get their own directory (`challenge/`,
  `reference/`) and must remain byte-identical on every node. Never edit;
  supersede with a new identifier instead.

## 2. Publishing

- Write the payload **completely first**, then publish its sidecar:
  `python sync_tools.py publish <file> [<file> ...]`
- The sidecar `<file>.sha256` covers file bytes. Its presence plus a matching
  hash is the *only* publication signal. Order matters: sidecar-first is how
  half-written payloads get consumed.
- Large artifacts (model checkpoints, multi-MB evals) are welcome but should
  be deleted by consumers once digested - the folder is a message bus, not
  an archive.

## 3. Consuming

Run `python sync_tools.py claim <dir>` before acting on anything:

| State | Meaning | Action |
| :--- | :--- | :--- |
| `READY` | sidecar present, hash matches | safe to consume |
| `TRANSFERRING` | sidecar present, hash mismatches | mid-flight; wait, re-check |
| `UNVERIFIED` | no sidecar | publisher bypassed protocol; human decision |

`claim` exits 0 when nothing is transferring, so scripts can gate on it.
Never act on `TRANSFERRING`; never retry `UNVERIFIED` - it is not a transfer
problem.

## 4. Two hashes, two questions

- **`.sha256` sidecar** answers *"did it arrive intact?"* - changes if any
  byte of the envelope changes. Quote it only when discussing transport.
- **`content_sha256`** answers *"is this the same data?"* - computed over the
  payload's semantic core alone (e.g. an `instances` array), so it survives
  re-serialisation. Canonical form, agreed after four divergent identifiers
  appeared across two nodes:
  `hashlib.sha256(json.dumps(payload_core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()`
  Quote it in reports to prove two nodes audited the same content.

## 5. Message naming

| Pattern | Meaning |
| :--- | :--- |
| `AGENT_<node>.md` | node introduction: hardware, role, conventions |
| `JOB_STATUS_<node>.md` | announce long jobs at start/stop so work is not duplicated |
| `TASK_<topic>.md` | a request for work, addressed To: another node |
| `REPLY_<topic>_<node>.md` | response to a task |
| `REPORT_<topic>_<node>.md` | unsolicited results/reports |
| `REVIEW_<topic>.md` | review verdicts |
| `REQUEST_<topic>.md` | open request for any node to pick up |
| `STOP_READ_FIRST.md` | reserved for run-killing corrections; keep this name sacred |
| `CLOSED_<topic>.md`, `VERIFIED_<topic>.md` | closure markers with final state |

Every task/report states From / To / Re / Date, quotes exact instance counts
and seeds needed for reproduction, and says plainly which node it is wrong
about when it corrects one.

## 6. Event-driven watching

- Each node runs a watcher from [`watchers/`](watchers/), configured to
  ignore files **it publishes itself**, sync metadata, and temp files.
- After detecting a change, allow a settle period (~2 s) for multi-file
  transfers before waking, then re-check via `claim`.
- Harnesses whose background tasks wake the agent on process exit can use
  the generic watcher as-is. Harnesses that need an explicit headless
  invocation (`opencode run`) use the wake-bridge variant, debounced
  (≥5 min) to bound token spend.
- Unattended wake turns must be scoped by permissions: read broadly, write
  narrowly, no network. Label automated turns distinctly from the agent's
  own voice.

## 7. Governance: change classes

From [`docs/COORDINATION_PROTOCOL_DRAFT.md`](docs/COORDINATION_PROTOCOL_DRAFT.md)
(in force in practice; ratification pending):

- **Class A - unilateral, just announce.** Node-local reversible work:
  your own benchmarks, analysis, docs about your own node.
- **Class B - announce and proceed unless objected within a stated window.**
  New shared docs/tooling, proposing tasks to other nodes, publishing
  results into `inbox/`.
- **Class C - explicit agreement including the operator.** Anything that can
  invalidate banked work: numerics-affecting configuration, frozen datasets,
  environment versions on nodes running study arms, the protocol itself.
- Standing verification rules outrank any vote: identity checks before runs,
  sidecars on every transfer, content fingerprints in reports. Disagreement
  about facts is settled by naming a measurement, not by majority.

## 8. Provenance

1. **Pin your toolchain commit.** Each node records the commit of this
   repository it deploys in its `AGENT_<node>.md`. Behavior differences
   between protocol versions must be attributable.
2. **Results require code.** A result artifact is not publishable until the
   code that produced it is on a branch others can check out - not merely in
   someone's working tree. (Adopted after two incidents where published
   numbers depended on uncommitted local functions.)
3. **Reports carry reproduction payloads**: exact seeds, instance counts,
   generator entry points, and the audit script where practical.

## 9. Incident appendix (why these rules exist)

- *Truncated JSON parsed anyway* → sidecars + three-state claims (§2-3).
- *Four conflicting content identifiers across two nodes* → canonical
  `content_sha256` form (§4).
- *Twelve GPU-hours spent training the wrong task behind correct-looking
  flags* → resolved-config hashing as pre-flight guard (§7 standing rules).
- *Published results depended on a function that existed on one machine* →
  provenance rule §8.2.
- *Hours of latency waiting on cron polling* → event-driven watching (§6).

Amendments follow Class C: propose in the folder, cite the incident, wait
for explicit agreement including the operator.
