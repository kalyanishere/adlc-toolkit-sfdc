# reconcile-pipeline-state

A pure-bash self-healer for "ghost" REQs — pipelines that shipped on
GitHub but whose `pipeline-state.json` was never finalized because the
runner died right at the end of Phase 8.

## What's a ghost?

| Symptom | Cause |
|---|---|
| Spec frontmatter says `status: complete` | Runner reached late Phase 8 |
| Merged PR exists on origin/main | `gh pr merge` succeeded |
| `pipeline-state.json` is missing or has `completed: false` | Runner exited before the final state-file write |
| Dashboard shows the REQ as "spec only" / "running" / "stalled" | …because no state file means no merged signal |

This script detects every ghost in a project and writes the minimum
state file the dashboard needs to render the REQ as `merged`. It
reconstructs the merge proof (PR url, merge commit sha, mergedAt) from
`gh pr list` (preferred) or `git log` (fallback for local-bare repos),
so the synthesized state is auditable.

## Usage

```sh
# Heal every ghost in the current project
sh tools/reconcile-pipeline-state/reconcile.sh

# Run against a specific project root
sh tools/reconcile-pipeline-state/reconcile.sh --root /path/to/project

# Show what would happen without writing
sh tools/reconcile-pipeline-state/reconcile.sh --dry-run --verbose
```

Exit codes:
- `0` — no ghosts, or all ghosts healed
- `1` — one or more ghosts could not be healed (e.g., merge commit not
        findable). The script logs each unhealable case and continues.
- `2` — usage error (bad arg, missing `jq`/`git`).

## What it does NOT do

- It does not run `/wrapup`. If lessons or assumptions weren't
  captured by the runner, this script won't synthesize them. Run
  `/wrapup REQ-xxx` afterwards if you need that.
- It does not delete worktrees, push commits, or modify any other
  artifact. Only `pipeline-state.json` files are written.
- It does not touch a healthy state file (`completed: true` and a
  non-empty `terminalState`) — those are skipped on every run.
- It does not look for in-flight runs. If a runner is currently
  writing the state file for an in-progress REQ, this script will
  see `completed: false` and may try to heal it. **Do not run during
  a live `/sprint`.** Run before kicking one off, or after it
  finishes.

## How healing works

For each spec dir whose `requirement.md` has `status: complete`:

1. Skip if `pipeline-state.json` already shows `completed: true` and
   a non-empty `terminalState` — already healthy, no-op.
2. Look up the merged PR. Try `gh pr list --state merged --search
   "head:feat/<REQ>-"` first; fall back to scanning local `main` for
   a squash-merge commit message starting with `<REQ-id>:`.
3. If neither path finds a merge, log a warning and skip — the script
   can't heal what it can't prove was merged.
4. Synthesize a state file via `jq`, merging over any partial state
   the runner did write so we don't lose its phase-history entries.
   The new file has:
   - `completed: true`
   - `terminalState: "merged"`
   - `currentPhase: 8`
   - `completedPhases: [0..8]`
   - `repos[<repo>]` with `merged: true`, the discovered `prUrl`,
     `mergedAt`, `mergeCommit`
   - A `reconciledAt` and `reconciledNotes` mark on the file so its
     synthetic origin is auditable.

## When to run

- **Before `/sprint`**: catches ghosts left from prior runs so the
  pre-flight selection sees a clean slate.
- **After `/sprint` reports "complete"**: catches ghosts the live
  sprint left behind, regardless of which runners crashed.
- **As a one-shot recovery** when you notice a stuck row on the
  sprint dashboard: run with `--verbose` to see exactly what it did.
