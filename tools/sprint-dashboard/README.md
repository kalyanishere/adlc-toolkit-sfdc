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

Each REQ card surfaces three time metrics:

| Pill                  | Source                                            | What it tells you                                                                  |
| --------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **Duration**          | `state.startedAt → now`                           | Wall-clock since the pipeline first ran. Includes idle gaps and pickup delays.     |
| **Active**            | `Σ (phase.completedAt − phase.startedAt)` + in-flight `(now − currentPhaseStartedAt)` | Real per-phase execution time. Excludes idle gaps. |
| **Last completion**   | `now − max(phaseHistory[*].completedAt)`          | How long since the most recent phase *finished*. Climbs during slow phases or stalls. |

Reading the gap between **Duration** and **Active** is the quickest way to spot a pipeline that ran briefly and then sat waiting (large Duration, small Active = pickup delay). For state files written before per-phase telemetry was added, **Active** falls back to a rough `startedAt → lastActivityAt` approximation and the tooltip says so.

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
