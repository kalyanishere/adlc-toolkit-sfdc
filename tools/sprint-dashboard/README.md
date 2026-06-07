# Sprint Dashboard

Zero-dependency, single-host, multi-project live dashboard for the ADLC pipeline. Reads every registered project's `.adlc/specs/*/pipeline-state.json` and renders a live view of REQs in flight — phase strip, per-phase telemetry, blockers, PR links, repo merge status.

## Quick reference

```
http://127.0.0.1:5174   # default URL
~/.adlc/dashboard-registry.json   # which projects show up
~/.adlc/runtime/sprint-dashboard.{pid,url,log}   # runtime state
```

## How projects get listed

The dashboard aggregates over `~/.adlc/dashboard-registry.json`:

```json
{
  "roots": [
    { "path": "/abs/path/to/project-a", "name": "project-a", "registeredAt": "..." },
    { "path": "/abs/path/to/project-b", "name": "project-b", "registeredAt": "..." }
  ]
}
```

Three ways a project lands in the registry:

1. **`/init`** — registers the current repo automatically (Step 10.5) and opens the dashboard in Chrome.
2. **Any `/spec`, `/proceed`, or `/sprint` invocation** — the launcher (`launch.sh`) upserts `$ADLC_ROOT` (default: `pwd`) into the registry on every run.
3. **Manual edit** — drop a `{path, name}` entry into the JSON. The server polls every ~1.5s, so it picks up the change without a restart.

The toolkit repo itself (anything containing `tools/sprint-dashboard/launch.sh`) is **not** auto-registered, since it's the development surface, not a project that hosts REQs. Override with `ADLC_FORCE_REGISTER=1` if you genuinely want it listed.

## Spec naming

Spec directories are detected with `/^(?:[A-Z]+-)?REQ-\d+/`, so both shapes work:

- `REQ-258-unified-retrieval-spec-pilot/` — un-prefixed (single-project usage)
- `SAT-REQ-010-tmp-pan-kyc-data-model/` — shortname-prefixed (`project.shortname` from `.adlc/config.yml`)

The prefix is preserved in the displayed REQ id so `SAT-REQ-010` stays distinct from a hypothetical `REQ-010` in another project.

## Telemetry pills

Each REQ card surfaces these time metrics:

| Pill                  | Source                                            | What it tells you                                                                  |
| --------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **Duration**          | `state.startedAt → now`                           | Wall-clock since the pipeline first ran. Includes idle gaps and pickup delays.     |
| **Active**            | `Σ (phase.completedAt − phase.startedAt)` + in-flight `(now − currentPhaseStartedAt)` | Real per-phase execution time. Excludes idle gaps. |
| **Last completion**   | `now − max(phaseHistory[*].completedAt)`          | How long since the most recent phase *finished*. Climbs during slow phases or stalls. |
| **User wait**         | Σ across `Stop → UserPromptSubmit` hook events attributed to this REQ's worktree session(s) | Cumulative time you spent at the prompt thinking before the next message. Live counter when a session is currently waiting. |

Reading the gap between **Duration** and **Active** is the quickest way to spot a pipeline that ran briefly and then sat waiting (large Duration, small Active = pickup delay). For state files written before per-phase telemetry was added, **Active** falls back to a rough `startedAt → lastActivityAt` approximation and the tooltip says so.

A project-level **summary bar** appears above the REQ list when any user-wait data has accrued — it shows cumulative wait across every session attributed to the project, plus a live `+Ns live (N session)` indicator that pulses while you're at the prompt.

### How User wait is captured

Two Claude Code hooks (added by `/init` to `.claude/settings.json`) append one JSONL event per turn boundary to `~/.adlc/runtime/user-wait.jsonl`:

```jsonl
{"ts":"2026-06-07T14:02:11Z","kind":"stop","session":"abc","cwd":"/repo/.worktrees/feat/SAT-REQ-006-foo"}
{"ts":"2026-06-07T14:18:44Z","kind":"submit","session":"abc","cwd":"/repo/.worktrees/feat/SAT-REQ-006-foo"}
```

The dashboard tails this log incrementally (byte-offset cursor; survives log rotation), groups events by `session`, and computes idle as `Σ (submit.ts − preceding stop.ts)`. Each session is attributed to:
- a **project**, via `cwd` prefix match against the registry
- a **REQ**, when `cwd` matches `<root>/.worktrees/<branch>/...` and the branch name embeds a REQ id

Sessions in non-worktree directories (e.g., editing the main checkout) still count toward the project rollup but don't attach to any single REQ.

**Caveats**: tool-permission prompts that block waiting for user approval are NOT captured (no public hook fires for them yet — run with `bypassPermissions` to avoid this gap, or accept it). Subagents share the parent's session id and don't fire their own turn boundaries, so `/sprint` running parallel REQs only attributes wait time correctly when each REQ is its own Claude Code process.

The schema fields powering this:

```json
{
  "startedAt": "...",
  "currentPhase": 4,
  "currentPhaseStartedAt": "...",
  "phaseHistory": [
    { "phase": 0, "name": "...", "startedAt": "...", "completedAt": "..." }
  ]
}
```

## UI controls

- **Project dropdown** (top of header) — switches the visible project. Selection persists in `localStorage`. Hidden when nothing is registered.
- **⟳ Refresh** — forces a fresh `GET /api/state`. Auto-refresh runs every ~1.5s via SSE; this is for forced refresh after editing the registry. Keyboard shortcut: `r` (ignores `Cmd/Ctrl+R`, which is browser reload, and any focus inside an input).
- **`updated HH:MM:SS`** — heartbeat next to the refresh button so it's visible whether the dashboard is alive.
- **Connection pill** (top-right) — `live` (green) / `reconnecting…` (red) / `connecting`.

## Server

Single Node.js process, no dependencies, shared across every project on the host.

```sh
# Manual launch (rarely needed — skills auto-launch)
sh tools/sprint-dashboard/launch.sh

# Open the dashboard in the browser at the same time
ADLC_DASHBOARD_OPEN=1 sh tools/sprint-dashboard/launch.sh

# Different port
ADLC_DASHBOARD_PORT=5180 sh tools/sprint-dashboard/launch.sh

# Force-register the toolkit repo (default: skipped)
ADLC_FORCE_REGISTER=1 sh tools/sprint-dashboard/launch.sh
```

Routes:

- `GET /` — single-page UI
- `GET /api/state` — JSON snapshot (`{ generatedAt, phaseLabels, projects: [...] }`)
- `GET /events` — SSE stream of `state` events on every state change

## Stopping it

```sh
kill "$(cat ~/.adlc/runtime/sprint-dashboard.pid)"
rm -f ~/.adlc/runtime/sprint-dashboard.{pid,url}
```

The server is `unref`'d-polling and `disown`'d at launch — it survives the parent shell exit. The next skill invocation transparently relaunches it if the process is gone.

## Logs

```sh
tail -f ~/.adlc/runtime/sprint-dashboard.log
```

Server-side errors are appended here; the launcher itself is silent on success.
