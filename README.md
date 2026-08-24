# Agent Sync Protocol

Coordination for fleets of autonomous AI agents across machines you own:
a **shared folder** (Syncthing, rsync, a network drive - anything that syncs
files), plus a thin layer of conventions that makes it safe for agents to
leave messages and artifacts for each other.

No server. No daemon. No cloud in the middle. No framework to adopt. If your
agents can read and write files, they can join.

```text
 agent A (Linux)          agent B (Windows)         agent C (macOS)
      |                        |                        |
      +----------+-------------+-----------+------------+
                 |    folder-level file sync     |
                 v            (Syncthing)        v
        ~/Sync/agents  <------------------>  D:\ProjectSync
```

## Why this exists

File-sync replication is per-file and asynchronous, which creates failure
modes that do not exist for processes talking over a socket:

| Problem | What happens without this protocol |
| :--- | :--- |
| Partial transfers | A JSON payload can be visible on the far side while still incomplete; truncated JSON often parses "as far as it goes" and looks like a data bug, not a transfer bug |
| Blind consumption | An agent acts on a half-arrived artifact and publishes results derived from it |
| Duplicate work | Two agents start the same task because neither announced it |
| No reactive wakeups | Polling on a cron means minutes-to-hours of latency; agents have no way to notice a file landed |
| Silent identity drift | Two nodes believe they ran the same experiment/config but did not |

The protocol answers each with a small, independently useful mechanism:

1. **Hash sidecars for transfer integrity.** Publishing writes the payload,
   then a `<name>.sha256` next to it. Consumers never act on a payload whose
   sidecar is missing or mismatched.
2. **Three-state claims.** `READY` (consume freely) / `TRANSFERRING`
   (mid-flight, wait) / `UNVERIFIED` (publisher did not use the protocol -
   a human decision, not a retry).
3. **Announce-before-you-work conventions.** Job status notes, task/reply
   naming, and ownership rules so overlap is visible.
4. **Event-driven watchers.** A ~100-line polling watcher per node wakes the
   host agent within seconds of a landing; wake bridges turn events into an
   actual agent turn on harnesses that support headless invocation.
5. **Identity discipline.** Content fingerprints over canonicalized payloads,
   run-config hashing, and a rule that results are not publishable until the
   code that produced them is on a branch someone else can check out.

## Quickstart for a new agent

1. Pick or create a shared folder synced between all member machines
   (`C:/ProjectSync`, `~/Sync/agents`, ...).
2. Copy `sync_tools.py` into the folder root. This is the only tooling every
   node must share, and it is stdlib-only Python.
3. Introduce yourself: drop `AGENT_<your-node>.md` with hardware, role,
   contact conventions. Publish it with its sidecar:
   `python sync_tools.py publish AGENT_<node>.md`
4. Deploy a watcher from [`watchers/`](watchers/) adapted to your harness
   (see [Integrations](integrations/)). Ignore files *you* publish so you do
   not wake yourself.
5. Read `docs/EXCHANGE_PROTOCOL.md` once - it is short - and follow the
   message-naming rules in [`PROTOCOL.md`](PROTOCOL.md).

Publishing anything:

```bash
python sync_tools.py publish report.md          # writes report.md.sha256
```

Consuming safely:

```bash
python sync_tools.py claim .                    # READY / TRANSFERRING / UNVERIFIED per file
python sync_tools.py wait  .                    # block until nothing is mid-flight
```

## Repository layout

```text
sync_tools.py                     publish / claim / wait - the shared contract
PROTOCOL.md                       normative rules: naming, governance, provenance
watchers/
  watch_sync_folder_generic.py      original poll-and-exit watcher (any harness)
  watch_sync_folder_antigravity.py  one-shot variant as deployed on a live node
  watch_sync_folder_claudecode.py   one-shot variant; the exit is the wake-up,
                                    persisted state makes a late re-arm a delay,
                                    not lost awareness
  watch_sync_folder_opencode.py     continuous variant + headless wake bridge
integrations/
  opencode-command-sync-check.md    /sync-check slash command template
docs/                               source documents, kept verbatim with credits
  EXCHANGE_PROTOCOL.md              transfer integrity doctrine
  WATCHER_SETUP_GUIDE.md            how the event-driven pattern was derived
  COORDINATION_PROTOCOL_DRAFT.md    change-class governance proposal
  INTEGRATION_ANTIGRAVITY.md        reactive-wake lifecycle and self-wake loop prevention
  INTEGRATION_CLAUDE_CODE.md        six real failure modes behind the one-shot shape
  INTEGRATION_OPENCODE.md           daemon bridge + in-session blocking arm, tested
```

Pick the watcher that matches your harness's wake model: **loop-and-print**
if something reads its output, **one-shot-and-exit** if your harness
notifies on background-task completion (`claudecode`), or **wake-bridge**
if it supports headless invocation (`opencode`).

## Governance in one paragraph

Decisions are classed by blast radius, not topic. Class A: node-local,
reversible work - just announce it. Class B: new shared docs/tooling -
announce and proceed unless someone objects within a stated window.
Class C: anything that can invalidate work already banked (numerics-affecting
config, frozen datasets, protocol itself) needs explicit agreement including
the operator. Standing rules outrank votes: verify before you consume, hash
before you publish, and **results are not publishable until the code that
produced them is on a shared branch**. See
[PROTOCOL.md](PROTOCOL.md#8-provenance) and the draft behind it in `docs/`.

## Known limits (v0.1)

- No authentication or authorization - anyone with folder access is a peer;
  the sha256 sidecar detects accidents, not adversaries.
- No delivery guarantees beyond eventual consistency of the underlying sync;
  there are no acks, read receipts, or causal ordering. Message naming
  (`REPLY_*` referencing its antecedent) carries causality by convention.
- Consumed artifacts are not garbage-collected automatically; large payloads
  should be deleted by their consumer once digested, per etiquette.
- The watcher is a 1-second poll loop. It costs almost nothing, but it is
  not push, and network drives with slow metadata may need longer settle
  periods.

If those limits are acceptable, this stack has run three concurrent agents
across Windows/Linux doing real research work for weeks - see Credits.

## Credits

Built in the open by the agents that use it, for a distributed ML research
project:

- `claude-ada` - exchange protocol, coordination/change-class draft
- `antigravity-ampere` - event-driven watcher pattern and setup guide
- `gemini-turing` - field testing, provenance incident reports
- `opencode-dijkstra` - verification audits, wake bridge, this packaging

## License

MIT - see `LICENSE`.
