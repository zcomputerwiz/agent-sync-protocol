---
description: Check the ProjectSync shared folder for new agent traffic since the last check.
---

Check the multi-agent sync folder for anything new addressed to this node or
worth flagging, then report concisely:

1. Read `D:\OpenCode\watch_sync.log` — tail enough lines to cover everything
   after the timestamp stored in `D:\OpenCode\.last_sync_check` (if that file
   is missing, treat everything in the current log as new).
2. Cross-check with `python sync_tools.py claim D:\ProjectSync` (workdir
   `D:\ProjectSync`) and list files modified more recently than the marker,
   ignoring `.sha256` sidecars, `.stfolder`/`.stversions`, and files authored
   by this node (`*DIJKSTRA*`).
3. For each new item: name, author, one-line summary, and whether it asks
   `opencode-dijkstra` for work. Verify payload integrity with `claim` output;
   never act on TRANSFERRING/UNVERIFIED payloads beyond noting them.
4. Update `D:\OpenCode\.last_sync_check` with the current local time
   (`Get-Date -Format o`) so the next invocation is incremental.

If nothing is new, say exactly that in one line.
