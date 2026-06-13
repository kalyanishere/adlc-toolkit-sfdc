# tools/git-dashboard

Static, git-committed companion to the live `tools/sprint-dashboard`.

The live dashboard is a Node server that polls local Claude transcripts and
shows in-flight progress. It only works on the machine that ran the pipeline
and disappears when the server stops.

This tool snapshots each REQ's pipeline state + token totals into JSON files
under `.adlc/metrics/` and rebuilds a self-contained `dashboard.html` that
opens directly in a browser (`file://` works — no server, no fetch). Once
committed alongside the rest of the wrapup, every clone of the repo gets the
same view.

## Files

- `snapshot.js` — generator. Reads `.adlc/specs/<REQ>/pipeline-state.json`
  and the local Claude transcripts (via the live dashboard's
  `token-usage.js`) and writes:
  - `.adlc/metrics/<REQ>.json` — per-REQ snapshot.
  - `.adlc/metrics/index.json` — rolled-up array used by the HTML.
  - `.adlc/metrics/dashboard.html` — regenerated from the template with
    `index.json` embedded inline.
- `dashboard.template.html` — UI template. The generator replaces the
  `<script id="adlc-metrics-data">` block with the current index payload.

## Usage

Run from the repo root (the tool finds `.adlc/` by walking up):

```bash
node tools/git-dashboard/snapshot.js --req REQ-258
node tools/git-dashboard/snapshot.js --all     # rebuild every REQ
```

`/wrapup` (Step 4a) calls the snapshot for the wrapping REQ and stages the
resulting metrics files in the same knowledge-capture commit that lands on
`main`.

### `--commit` mode (in-flight milestones)

`/proceed` calls the script at two milestones with `--commit` so teammates
see in-flight REQs without running anything locally:

| Milestone | When | Commit message |
| --- | --- | --- |
| `phase-0-started` | end of Phase 0 (REQ initialized) | `chore(REQ-xxx): metrics snapshot — phase-0-started` |
| `phase-5-verify` | start of Phase 5 (entering review) | `chore(REQ-xxx): metrics snapshot — phase-5-verify` |
| `phase-8-wrapup` | `/wrapup` Step 4b (no `--commit`; bundled into the knowledge commit) | `chore(REQ-xxx): capture knowledge…` |

```bash
node tools/git-dashboard/snapshot.js --req REQ-258 --milestone phase-0-started --commit
```

What `--commit` does, in order, under a cooperative `mkdir`-lock so concurrent
`/sprint` runners serialize on the push:

1. Write the per-REQ JSON.
2. `git fetch origin <branch>`. If we're behind: stash any unrelated
   working-tree changes, `git pull --rebase`, regenerate aggregates from
   the pulled per-REQ files, pop the stash.
3. `git add .adlc/metrics/`. If nothing actually changed, exit cleanly.
4. `git commit` with the milestone-labelled subject.
5. `git push origin <branch>`.

Every failure is **non-fatal**. The script logs a warning and exits 0 so
`/proceed` and `/sprint` never block on a metrics push. If push is blocked
by branch protection on `main`, the local commit lands and the next
milestone push will catch it up. Pass `--no-push` to test the commit path
without actually pushing.

`--commit` requires the working tree at `--root` to be on `main` or
`master`. Calling it from a feature worktree is a no-op — the script
warns and exits. `/proceed`'s Phase 5 hook is responsible for resolving
`repos[<primary>].path` from `pipeline-state.json` and passing it as
`--root` so the commit lands on `main` even when Phase 5 is running
inside a worktree.

## Token data

Tokens are best-effort. The aggregator reads
`~/.claude/projects/<flattened-cwd>/*.jsonl` filtered to the REQ's pipeline
session id. Snapshots taken on a fresh clone (or after the local transcript
has been pruned) write `tokens.captured = false` with a reason — the
dashboard renders `—` for those rows. Re-running the snapshot on a machine
that still has the transcripts will fill them in.
