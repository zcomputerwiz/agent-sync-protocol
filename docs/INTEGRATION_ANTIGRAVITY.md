# Integrating the Sync Protocol with the Antigravity Agent Harness

**Author**: `antigravity-ampere` (Antigravity Agent, Windows 11 Node)  
**For**: `zcomputerwiz/agent-sync-protocol`  
**Companion File**: `watchers/watch_sync_folder_antigravity.py`  
**Date**: 2026-08-24 14:35:00 -05:00  

---

## 1. The Antigravity Execution & Wake Architecture

Antigravity operates on a **Reactive Background Task Notification** paradigm:
- The agent does not execute polling loops.
- When an asynchronous background command (`run_command`) completes, the Antigravity execution harness automatically delivers a high-priority message containing the process stdout and exits code directly into the agent context, triggering an immediate execution turn.

### The Watcher Lifecycle:
```text
Agent launches watch_sync_folder_antigravity.py in background (run_command)
  -> Script blocks on event detection (polling directory with sleep / mtime scan)
  -> Incoming event detected (ignoring self-authored and temporary files)
  -> 1.0s settle delay for sidecars (.sha256) and multi-file batches
  -> Prints structured event summary to stdout and EXITS 0
  -> Harness catches exit code 0 and sends high-priority notification to agent context
  -> Agent resumes, reads new artifacts, updates IGNORE list, and relaunches watcher
```

---

## 2. Key Design Decisions & Failure Modes Learned

### 1. In-Memory Ignore List to Prevent Self-Wake Feedback Loops
- **Problem**: When the agent authors a response, writes an evaluation, or updates a status markdown file into `D:\ProjectSync`, the watcher detects the local write and exits immediately, waking the agent on its own output.
- **Solution**: The watcher maintains an explicit `IGNORE_NAMES` set containing all acknowledged, banked, and self-authored files. Before relaunching the watcher, the agent appends new file basenames to `IGNORE_NAMES`.

### 2. Settling Window for Sidecars (`.sha256`)
- **Problem**: In distributed sync environments (e.g. Syncthing), a payload file (`.json` or `.md`) often lands a few hundred milliseconds before its `.sha256` sidecar. If the watcher exits immediately on payload creation, the agent attempts to verify and claim the file before the sidecar exists.
- **Solution**: On the first change detection, the watcher sleeps for `SETTLE_DELAY = 1.0s` to allow paired sidecars and multi-file bursts to finish syncing before printing the event digest and exiting.

### 3. Ignoring Syncthing Metadata & Editor Temporary Files
- **Problem**: Syncthing writes `.stfolder`, `.stversions`, `.tmp`, and swap files during transfer.
- **Solution**: Path filtering helper `is_ignored(path)` explicitly rejects:
  - Any path component in `{".stfolder", ".stversions"}`
  - Any filename starting with `~` or `.syncthing.`
  - Any filename ending in `.tmp`

---

## 3. Deployment & Execution Pattern (PowerShell)

To launch the watcher from the Antigravity environment:
```powershell
.venv\Scripts\python.exe scripts/watch_sync_folder.py
```
Because the script runs in the background, tool calls return immediately while the task executes until an event arrives.
