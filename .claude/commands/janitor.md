---
description: Run the code-janitor subagent on the current repo to produce a cleanup-candidate report.
---

Launch the `code-janitor` subagent on this repository. It will scan for
unreferenced files, dead code, stale TODOs, and abandoned experiments,
and return a structured report.

The janitor never deletes anything on its own. After you read the report,
tell me which items to remove and I'll stage a deletion PR.

$ARGUMENTS
