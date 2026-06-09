#!/usr/bin/env node
// ADLC sprint dashboard — zero-dep multi-project SSE server.
// Reads ~/.adlc/dashboard-registry.json on every poll and aggregates
// .adlc/specs/{,<PFX>-}REQ-*/ across every registered project root.
// (Optional [A-Z]+- prefix lets shortname-namespaced ids like SAT-REQ-010 match.)
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

const HOME = os.homedir();
const HOME_RUNTIME = path.join(HOME, '.adlc', 'runtime');
const PID_FILE = path.join(HOME_RUNTIME, 'sprint-dashboard.pid');
const PORT_FILE = path.join(HOME_RUNTIME, 'sprint-dashboard.port');
const URL_FILE = path.join(HOME_RUNTIME, 'sprint-dashboard.url');
const LOG_FILE = path.join(HOME_RUNTIME, 'sprint-dashboard.log');
const REGISTRY_FILE = path.join(HOME, '.adlc', 'dashboard-registry.json');
// JSONL written by Stop / UserPromptSubmit hooks (one event per turn
// boundary, per Claude Code session). Aggregated below to compute
// user-wait idle time at session, project, and REQ granularities.
const USER_WAIT_LOG = path.join(HOME_RUNTIME, 'user-wait.jsonl');

const PORT = parseInt(process.env.ADLC_DASHBOARD_PORT || '5174', 10);
const HOST = '127.0.0.1';
const POLL_MS = 1500;
// Threshold for flagging a REQ as "stalled" — measured from
// the most recent phaseHistory completion (lastActivityAt) and from
// currentPhaseStartedAt for the in-flight phase. Defaults to 5 minutes.
// Tune via ADLC_DASHBOARD_STALL_SECONDS for projects with naturally slow
// phases (e.g. a multi-minute Apex test phase).
const STALL_THRESHOLD_SEC = parseInt(process.env.ADLC_DASHBOARD_STALL_SECONDS || '300', 10);

// Cap on the "currently-waiting" live window. The Stop hook fires when Claude
// finishes a turn; UserPromptSubmit fires when the user submits the next
// prompt. If the user closes the terminal (SIGKILL, machine sleep, Ctrl-D)
// without ever submitting again, no Submit event ever closes the bucket and
// `now - lastStopAt` grows forever, dwarfing real user-wait time on the
// dashboard. Past this cap we treat the session as no longer waiting (it's
// realistically gone). 6h default — tune via ADLC_DASHBOARD_LIVE_WAIT_CAP_HOURS.
// Set to 0 to disable the cap (unbounded live windows).
const LIVE_WAIT_CAP_MS = (() => {
  const h = parseFloat(process.env.ADLC_DASHBOARD_LIVE_WAIT_CAP_HOURS || '6');
  return Number.isFinite(h) && h > 0 ? Math.round(h * 3600 * 1000) : 0;
})();

const HTML_PATH = path.join(__dirname, 'index.html');

const PHASE_LABELS = [
  '0 Worktree',
  '1 Spec',
  '2 Architect',
  '3 Validate',
  '4 Implement',
  '5 Verify',
  '6 PR',
  '7 CI',
  '8 Merge',
];

function log(msg) {
  try {
    fs.appendFileSync(LOG_FILE, `[${new Date().toISOString()}] ${msg}\n`);
  } catch (_) { /* no-op */ }
}

function ensureHomeRuntime() {
  fs.mkdirSync(HOME_RUNTIME, { recursive: true });
}

function readJsonSafe(file) {
  try {
    const txt = fs.readFileSync(file, 'utf8');
    if (!txt.trim()) return null;
    return JSON.parse(txt);
  } catch (_) {
    return null;
  }
}

function readRegistry() {
  const data = readJsonSafe(REGISTRY_FILE);
  if (!data || !Array.isArray(data.roots)) return [];
  const seen = new Set();
  const roots = [];
  for (const r of data.roots) {
    if (!r || typeof r.path !== 'string') continue;
    if (seen.has(r.path)) continue;
    seen.add(r.path);
    roots.push({
      path: r.path,
      name: typeof r.name === 'string' && r.name ? r.name : path.basename(r.path),
      registeredAt: r.registeredAt || null,
    });
  }
  return roots;
}

const REQ_DIR_RE = /^(?:[A-Z]+-)?REQ-\d+/;

function listSpecDirs(root) {
  const specsRoot = path.join(root, '.adlc', 'specs');
  if (!fs.existsSync(specsRoot)) return [];
  let entries;
  try { entries = fs.readdirSync(specsRoot); } catch (_) { return []; }
  return entries
    .filter((name) => REQ_DIR_RE.test(name))
    .map((name) => path.join(specsRoot, name));
}

// Walk every worktree under <root>/.worktrees/* and collect any REQ spec
// directories living there. /proceed Step 0 writes pipeline-state.json
// into the *worktree's* .adlc/specs/REQ-xxx/ before the work merges back
// to main, so without scanning worktrees the dashboard can't see in-flight
// REQs. Their state files are the live ones — once Phase 8 merges the PR,
// the worktree is removed and the merged copy in <root>/.adlc/specs/ takes
// over. Tolerant of missing/empty .worktrees and unreadable subdirs.
function listWorktreeSpecDirs(root) {
  const worktreesRoot = path.join(root, '.worktrees');
  if (!fs.existsSync(worktreesRoot)) return [];
  let worktrees;
  try { worktrees = fs.readdirSync(worktreesRoot); } catch (_) { return []; }
  const out = [];
  for (const wt of worktrees) {
    const wtPath = path.join(worktreesRoot, wt);
    let stat;
    try { stat = fs.statSync(wtPath); } catch (_) { continue; }
    if (!stat.isDirectory()) continue;
    const specsRoot = path.join(wtPath, '.adlc', 'specs');
    if (!fs.existsSync(specsRoot)) continue;
    let entries;
    try { entries = fs.readdirSync(specsRoot); } catch (_) { continue; }
    for (const name of entries) {
      if (REQ_DIR_RE.test(name)) out.push(path.join(specsRoot, name));
    }
  }
  return out;
}

function reqIdFromSpecDir(specDir) {
  const m = path.basename(specDir).match(/^((?:[A-Z]+-)?REQ-\d+)/);
  return m ? m[1] : path.basename(specDir);
}

function readReqTitle(specDir) {
  const reqFile = path.join(specDir, 'requirement.md');
  if (!fs.existsSync(reqFile)) return '';
  try {
    const txt = fs.readFileSync(reqFile, 'utf8');
    const titleMatch = txt.match(/^title:\s*(.+)$/m) ||
      txt.match(/^#\s+(.+)$/m);
    return titleMatch ? titleMatch[1].trim().replace(/^["']|["']$/g, '') : '';
  } catch (_) {
    return '';
  }
}

function readTaskStrip(specDir) {
  const tasksDir = path.join(specDir, 'tasks');
  if (!fs.existsSync(tasksDir)) return [];
  let files;
  try {
    files = fs.readdirSync(tasksDir)
      .filter((f) => /^TASK-.*\.md$/.test(f))
      .sort();
  } catch (_) { return []; }
  return files.map((f) => {
    let txt = '';
    try { txt = fs.readFileSync(path.join(tasksDir, f), 'utf8'); } catch (_) {}
    // TASK ids may carry a REQ-numbered prefix segment, e.g.
    // TASK-010-001-tmp-applicant-object.md → id "TASK-010-001". Match
    // any sequence of "-<digits>" runs after the literal "TASK-" so
    // TASK-001, TASK-010-001, and TASK-010-001-002 all parse correctly.
    const idMatch = f.match(/^(TASK(?:-\d+)+)/);
    const statusMatch = txt.match(/^status:\s*(.+)$/m);
    const titleMatch = txt.match(/^title:\s*(.+)$/m) ||
      txt.match(/^#\s+(.+)$/m);
    return {
      id: idMatch ? idMatch[1] : f.replace(/\.md$/, ''),
      status: statusMatch ? statusMatch[1].trim() : 'unknown',
      title: titleMatch ? titleMatch[1].trim().replace(/^["']|["']$/g, '') : '',
    };
  });
}

// Last-known-good state cache. Keyed by `<rootPath>::<reqId>`. The cache
// holds the most recent stateful snapshot we've seen for a given REQ —
// independent of whether the underlying file currently exists on disk.
//
// Why this exists: under the new contract `pipeline-state.json` lives in
// the main checkout for the entire run (and survives worktree removal),
// but for legacy pipelines started under the old contract the only
// state file is inside a worktree that Phase 8 cleanup removes. Without
// this cache, a removed worktree causes the REQ to revert to "spec only
// — pipeline not started" on the dashboard, which is wrong for a REQ
// that had been mid-flight. With this cache, the last observed snapshot
// stays visible (with a stale=true flag the UI can surface) until the
// reconciler writes a finalized file to the main checkout.
const lastKnownState = new Map();

// Sidecar state written by `/spec`, `/architect`, and `/validate` so the
// dashboard can show a REQ's spec/architecture phases as green BEFORE
// `/proceed` runs. Schema is minimal:
//   { completedPhases: number[], phaseHistory?: [{phase, name, completedAt}] }
// Phase indices match the canonical pipeline (1=spec validated, 2=architect
// validated). The dashboard merges this into the rendered state — pipeline
// state always wins on conflict; sidecar only fills in phases /proceed
// hasn't recorded yet.
function readValidationSidecar(specDir) {
  const f = path.join(specDir, 'validation-state.json');
  const v = readJsonSafe(f);
  if (!v || typeof v !== 'object') return null;
  const completedPhases = Array.isArray(v.completedPhases)
    ? v.completedPhases.filter((n) => Number.isInteger(n) && n >= 0 && n <= 8)
    : [];
  const phaseHistory = Array.isArray(v.phaseHistory) ? v.phaseHistory : [];
  return { completedPhases, phaseHistory };
}

function projectReqState(specDir, opts = {}) {
  const id = path.basename(specDir).match(/^((?:[A-Z]+-)?REQ-\d+)/);
  const reqId = id ? id[1] : path.basename(specDir);
  const stateFile = path.join(specDir, 'pipeline-state.json');
  const state = readJsonSafe(stateFile);
  const sidecar = readValidationSidecar(specDir);
  const cacheKey = `${opts.rootPath || ''}::${reqId}`;

  const title = readReqTitle(specDir);
  const tasks = readTaskStrip(specDir);

  if (!state) {
    // No live state file. Two sub-cases matter for the dashboard:
    //
    //   (a) Spec exists but pipeline has never run — render as "spec only"
    //       (the legitimate "yet to start" case).
    //   (b) Pipeline WAS running and we have a cached last-known snapshot
    //       — the worktree was probably removed (Phase 8 cleanup) before
    //       state was finalized to the main checkout, OR a legacy run is
    //       in flight without main-checkout state. Render the cached
    //       snapshot with `stale: true` so the UI can mark it as
    //       "last known: phase N — file gone, awaiting reconciliation".
    //       Never regress to "yet to start" — that's the bug we're
    //       fixing.
    const cached = lastKnownState.get(cacheKey);
    if (cached) {
      return {
        ...cached,
        title: title || cached.title,
        tasks,                    // refresh tasks from disk every snapshot
        stale: true,
        staleReason: 'pipeline-state.json no longer present on disk; showing last observed snapshot. Run `tools/reconcile-pipeline-state/reconcile.sh` if the REQ has merged but the dashboard hasn\'t finalized.',
      };
    }
    // No pipeline-state. If a validation sidecar is present (from /spec,
    // /architect, /validate), surface its completed phases so the phase
    // strip renders green for validated work even before /proceed kicks off.
    const sideCompleted = sidecar?.completedPhases || [];
    const sideHistory = sidecar?.phaseHistory || [];
    const lastSideAt = sideHistory
      .map((p) => (p && typeof p.completedAt === 'string') ? p.completedAt : null)
      .filter(Boolean)
      .sort()
      .pop() || null;
    return {
      reqId,
      title,
      hasState: sideCompleted.length > 0,
      currentPhase: sideCompleted.length ? Math.min(8, Math.max(...sideCompleted) + 1) : null,
      completed: false,
      blockers: [],
      currentTask: null,
      failedTasks: [],
      completedTasks: [],
      completedPhases: sideCompleted,
      lastPhase: sideHistory.length ? sideHistory[sideHistory.length - 1] : null,
      startedAt: null,
      lastActivityAt: lastSideAt,
      currentPhaseStartedAt: null,
      activeMs: 0,
      hasPhaseTelemetry: false,
      integrationBranch: null,
      repos: {},
      tasks,
      schemaViolations: [],
      stalled: false,
      stalledSeconds: 0,
      stallThresholdSec: STALL_THRESHOLD_SEC,
      stale: false,
      validationOnly: sideCompleted.length > 0,
    };
  }

  const repos = {};
  if (state.repos && typeof state.repos === 'object') {
    for (const [k, v] of Object.entries(state.repos)) {
      if (!v || typeof v !== 'object') continue;
      repos[k] = {
        touched: !!v.touched,
        merged: !!v.merged,
        prUrl: v.prUrl || null,
        primary: !!v.primary,
        branch: v.branch || null,
      };
    }
  }

  const phaseHistory = Array.isArray(state.phaseHistory) ? state.phaseHistory : [];
  // Latest `completedAt` across phaseHistory — proxy for "when did this spec
  // last advance?". Used by the dashboard to surface pickup-delay/idle vs
  // active execution time. We sort lexicographically because every value
  // is an ISO-8601 string (UTC), so lex order == chronological order.
  const lastActivityAt = phaseHistory
    .map((p) => (p && typeof p.completedAt === 'string') ? p.completedAt : null)
    .filter(Boolean)
    .sort()
    .pop() || null;

  // Per-phase telemetry. Modern state files (post-REQ-XXX) record each
  // phaseHistory entry with both startedAt and completedAt, plus a
  // top-level currentPhaseStartedAt for the in-flight phase.
  // The dashboard sums per-phase active spans + the live in-flight span
  // to report real execution time (which excludes idle gaps between
  // phases / pickup delays). Legacy entries that lack startedAt
  // contribute 0 to the sum — they show up only in idle/wall-clock.
  let activeMs = 0;
  let hasPhaseTelemetry = false;
  for (const p of phaseHistory) {
    if (!p || typeof p.startedAt !== 'string' || typeof p.completedAt !== 'string') continue;
    const a = Date.parse(p.startedAt);
    const b = Date.parse(p.completedAt);
    if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) continue;
    activeMs += (b - a);
    hasPhaseTelemetry = true;
  }
  const currentPhaseStartedAt = typeof state.currentPhaseStartedAt === 'string'
    ? state.currentPhaseStartedAt
    : null;

  // Schema-violation healing. The pipeline-runner is supposed to write
  // currentPhase as a number 0..8 and completedPhases as an int array,
  // but stray runs have written e.g. "phase-3-validate-architecture"
  // and omitted completedPhases entirely. Without healing, the phase
  // strip and the "Phase N / 8" line silently render nothing — which
  // looks like a stalled pipeline. Coerce here, surface the violation
  // alongside the data so the UI can flag it.
  const schemaViolations = [];
  let currentPhase = null;
  // Terminal-state words a runner sometimes writes when it should be
  // setting completed:true and currentPhase:8 instead.
  const terminalWords = new Set(['merged', 'complete', 'completed', 'done', 'wrapup']);
  if (typeof state.currentPhase === 'number' && Number.isInteger(state.currentPhase)) {
    currentPhase = state.currentPhase;
  } else if (typeof state.currentPhase === 'string') {
    const m = state.currentPhase.match(/(\d+)/);
    const lower = state.currentPhase.toLowerCase();
    if (m) {
      currentPhase = Number(m[1]);
      schemaViolations.push(`currentPhase was string "${state.currentPhase}" — coerced to ${currentPhase}`);
    } else if (terminalWords.has(lower)) {
      currentPhase = 8;
      schemaViolations.push(`currentPhase was terminal-state string "${state.currentPhase}" — coerced to 8 (Phase 8 is the canonical end). Runner should set completed:true and currentPhase:8 separately.`);
    } else {
      schemaViolations.push(`currentPhase was string "${state.currentPhase}" with no numeric component`);
    }
  } else if (state.currentPhase != null) {
    schemaViolations.push(`currentPhase had unexpected type ${typeof state.currentPhase}`);
  }
  // If completed is true but currentPhase couldn't be resolved, default
  // to 8 — the canonical end. Otherwise the phase strip is empty for
  // already-merged REQs whose state files have a malformed currentPhase.
  if (currentPhase === null && state.completed === true) {
    currentPhase = 8;
  }
  // Conversely: if state has terminal-word currentPhase but no explicit
  // `completed: true`, infer completion. The runner clearly thought the
  // pipeline was done.
  const inferCompleted = (typeof state.currentPhase === 'string' && terminalWords.has(state.currentPhase.toLowerCase())) || state.completed === true;

  // Helper: extract a phase index 0..8 from either a number or a string
  // like "phase-3-validate-architecture". Returns null when no integer
  // can be recovered.
  const phaseIndex = (v) => {
    if (Number.isInteger(v)) return v;
    if (typeof v === 'string') {
      const m = v.match(/(\d+)/);
      if (m) return Number(m[1]);
    }
    return null;
  };

  let completedPhases;
  if (Array.isArray(state.completedPhases)) {
    completedPhases = state.completedPhases.filter((n) => Number.isInteger(n));
  } else {
    // Reconstruct from phaseHistory[*].phase as a best-effort fallback
    // when the runner forgot to write completedPhases at all.
    completedPhases = phaseHistory
      .map((p) => (p ? phaseIndex(p.phase) : null))
      .filter((n) => n != null);
    if (state.completedPhases !== undefined) {
      schemaViolations.push(`completedPhases had unexpected type ${typeof state.completedPhases}`);
    } else if (completedPhases.length) {
      schemaViolations.push(`completedPhases missing from state — reconstructed ${completedPhases.length} entry/entries from phaseHistory`);
    }
  }

  // Per-phase activeMs sum needs the same string-tolerant reading.
  // (The earlier loop already accepts string startedAt/completedAt; the
  // p.phase coercion is purely informational here, but reconstructing
  // completedPhases from string-form phaseHistory is the user-visible
  // win — the phase strip lights up correctly even when the runner
  // wrote bad shapes.)

  // Stall detection. The dashboard already tracks "Last completion"
  // (now − lastActivityAt) and the in-flight phase span
  // (now − currentPhaseStartedAt). Whichever signal is MORE recent is
  // the right indicator that the pipeline is actively progressing —
  // a phase that just started has currentPhaseStartedAt close to now,
  // and a phase that just completed has lastActivityAt close to now.
  // Take the max of the two and treat (now - max) as the stall age.
  // Skip stall detection on completed REQs (they're at rest).
  let stalledSeconds = 0;
  let stalled = false;
  if (!inferCompleted) {
    const candidates = [lastActivityAt, currentPhaseStartedAt]
      .filter((s) => typeof s === 'string')
      .map((s) => Date.parse(s))
      .filter(Number.isFinite);
    if (candidates.length) {
      const mostRecent = Math.max(...candidates);
      stalledSeconds = Math.floor((Date.now() - mostRecent) / 1000);
      if (stalledSeconds >= STALL_THRESHOLD_SEC) stalled = true;
    }
  }

  // Merge in any pre-/proceed validation sidecar phases. /spec, /architect,
  // /validate write phases 1 and 2 here; if the live pipeline-state didn't
  // record those (e.g. /proceed picked up mid-flow without seeing /validate's
  // stamp), keep them green on the strip.
  if (sidecar?.completedPhases?.length) {
    const seen = new Set(completedPhases);
    for (const p of sidecar.completedPhases) {
      if (!seen.has(p) && p < (currentPhase ?? 9)) {
        completedPhases.push(p);
        seen.add(p);
      }
    }
    completedPhases.sort((a, b) => a - b);
  }

  const result = {
    reqId,
    title,
    hasState: true,
    currentPhase,
    completed: inferCompleted,
    blockers: Array.isArray(state.blockers) ? state.blockers : [],
    currentTask: state.phase4?.currentTask || null,
    failedTasks: Array.isArray(state.phase4?.failedTasks) ? state.phase4.failedTasks : [],
    completedTasks: Array.isArray(state.phase4?.completedTasks) ? state.phase4.completedTasks : [],
    completedPhases,
    lastPhase: phaseHistory.length ? phaseHistory[phaseHistory.length - 1] : null,
    startedAt: state.startedAt || null,
    lastActivityAt,
    currentPhaseStartedAt,
    activeMs,
    hasPhaseTelemetry,
    integrationBranch: state.integrationBranch || null,
    repos,
    tasks,
    schemaViolations,
    stalled,
    stalledSeconds,
    stallThresholdSec: STALL_THRESHOLD_SEC,
    stale: false,
  };
  // Cache the latest stateful snapshot so a subsequent disappearance of
  // the file (typical worktree-cleanup-before-finalization case) keeps
  // the REQ visible at its last known phase rather than reverting it to
  // "yet to start". See the no-state branch above for how the cache is
  // surfaced. Strip the live `tasks` array — it's re-read from disk on
  // every snapshot; caching it would freeze task status alongside phase.
  const { tasks: _tasksDrop, ...cacheable } = result;
  lastKnownState.set(cacheKey, cacheable);
  return result;
}

// =============================================================================
// User-wait tracking
// =============================================================================
//
// The Stop / UserPromptSubmit hooks (templates/claude-settings-template.json)
// append one JSONL event per turn boundary, e.g.:
//   {"ts":"2026-06-07T14:02:11Z","kind":"stop","session":"abc","cwd":"/repo"}
//   {"ts":"2026-06-07T14:18:44Z","kind":"submit","session":"abc","cwd":"/repo"}
//
// We tail the file incrementally (track byte offset) and accumulate per-session
// idle time. A "session" idle epoch starts at a `stop` and ends at the next
// `submit` for the same session id; the delta is added to that session's
// totalIdleMs. Sessions still in stop at snapshot time contribute a live
// `currentlyWaitingMs = now - lastStopAt`.
//
// Each session is also attributed to:
//   - a registered project root (via cwd prefix match), or null if none
//   - a REQ id, when the cwd lives under <root>/.worktrees/<branch>/...
//     where <branch> contains a REQ id (best-effort, regex-based)
//
// Both attributions are recomputed every snapshot — a session's cwd never
// actually changes (Claude Code processes don't chdir between turns), but
// new sessions arrive constantly so it's cheaper to recompute than invalidate.
//
// Bucket key is `${session}::${cwd}`, NOT just `session`. Real-world hooks
// frequently emit `session:"unknown"` (CLAUDE_SESSION_ID isn't always
// exported into the hook's environment, especially for sub-agents and in
// some shell variants). Without including cwd, every "unknown" event from
// every project collapses into a single bucket whose cwd is whichever
// project happened to fire the first event — and every other project
// reports zeroed user-wait. Adding cwd to the key gives each project (and
// each worktree) its own bucket, which is what the per-project /
// per-REQ aggregation actually needs.

const userWaitBySession = new Map();
let userWaitOffset = 0;

function ingestUserWaitLog() {
  let stat;
  try { stat = fs.statSync(USER_WAIT_LOG); } catch (_) { return; }
  // File rotated/truncated → reset cursor to start of (now smaller) file.
  if (stat.size < userWaitOffset) userWaitOffset = 0;
  if (stat.size === userWaitOffset) return;

  let buf;
  try {
    const fd = fs.openSync(USER_WAIT_LOG, 'r');
    buf = Buffer.alloc(stat.size - userWaitOffset);
    fs.readSync(fd, buf, 0, buf.length, userWaitOffset);
    fs.closeSync(fd);
  } catch (_) { return; }
  userWaitOffset = stat.size;

  for (const line of buf.toString('utf8').split('\n')) {
    if (!line) continue;
    let ev;
    try { ev = JSON.parse(line); } catch (_) { continue; }
    if (!ev || typeof ev.session !== 'string' || typeof ev.kind !== 'string') continue;
    const tsMs = Date.parse(ev.ts);
    if (!Number.isFinite(tsMs)) continue;
    const key = `${ev.session}::${ev.cwd || ''}`;
    let s = userWaitBySession.get(key);
    if (!s) {
      s = {
        cwd: ev.cwd || '',
        firstSeenAt: tsMs,
        lastEventAt: tsMs,
        lastStopAt: null,
        totalIdleMs: 0,
        turnCount: 0,
      };
      userWaitBySession.set(key, s);
    }
    if (ev.cwd && !s.cwd) s.cwd = ev.cwd;
    s.lastEventAt = tsMs;
    if (ev.kind === 'stop') {
      // First stop after a submit (or initial stop) opens a wait window.
      // Two stops in a row (interrupt-style) keep the EARLIEST as the
      // start so a user who Esc'd during a tool call still gets full credit
      // for their think time.
      if (!s.lastStopAt) s.lastStopAt = tsMs;
    } else if (ev.kind === 'submit') {
      if (s.lastStopAt) {
        s.totalIdleMs += Math.max(0, tsMs - s.lastStopAt);
        s.lastStopAt = null;
      }
      s.turnCount++;
    }
  }
}

// Extract a REQ id from a worktree path. Worktrees live at
// <root>/.worktrees/<branch>/... and the branch name typically embeds the
// REQ id, e.g. .worktrees/feat/SAT-REQ-006-foo/. Returns null when the cwd
// isn't a worktree path or no REQ id is recoverable.
function reqIdFromCwd(cwd) {
  if (!cwd) return null;
  const wtIdx = cwd.indexOf(`${path.sep}.worktrees${path.sep}`);
  if (wtIdx < 0) return null;
  const after = cwd.slice(wtIdx + `${path.sep}.worktrees${path.sep}`.length);
  const m = after.match(/((?:[A-Z]+-)?REQ-\d+)/);
  return m ? m[1] : null;
}

// Map a session's cwd onto the registered project root it belongs to.
// Worktree sessions (cwd = <root>/.worktrees/<branch>/...) attribute back
// to <root>. Returns null if no registered project matches.
function attributeToRoot(cwd, roots) {
  if (!cwd) return null;
  for (const r of roots) {
    if (cwd === r.path || cwd.startsWith(r.path + path.sep)) return r.path;
  }
  return null;
}

// Aggregate user-wait totals across all sessions attributed to this root.
// Returns a per-project summary plus a map of REQ-id → per-REQ summary so
// the dashboard can surface idle time at the REQ card level.
function userWaitFor(rootPath, nowMs) {
  let totalMs = 0;
  let waitingMs = 0;
  let waitingSessions = 0;
  let activeSessions = 0;
  let totalTurns = 0;
  const byReq = {};
  for (const [sid, s] of userWaitBySession) {
    if (s._rootCache !== rootPath) continue;
    activeSessions++;
    totalMs += s.totalIdleMs;
    totalTurns += s.turnCount;
    let liveMs = 0;
    if (s.lastStopAt) {
      const rawLive = Math.max(0, nowMs - s.lastStopAt);
      // Cap the live window: a Stop with no follow-up Submit grows forever
      // when the user closes the terminal without exiting Claude properly.
      // Past LIVE_WAIT_CAP_MS we treat the session as gone and stop counting it
      // toward the live counter. Set ADLC_DASHBOARD_LIVE_WAIT_CAP_HOURS=0 to
      // disable the cap entirely.
      const liveBeyondCap = LIVE_WAIT_CAP_MS > 0 && rawLive > LIVE_WAIT_CAP_MS;
      if (!liveBeyondCap) {
        liveMs = rawLive;
        waitingMs += liveMs;
        waitingSessions++;
      }
    }
    const reqId = s._reqCache;
    if (reqId) {
      const slot = byReq[reqId] || (byReq[reqId] = {
        totalMs: 0, waitingMs: 0, waitingSessions: 0, turns: 0,
      });
      slot.totalMs += s.totalIdleMs;
      slot.turns += s.turnCount;
      if (liveMs) {
        slot.waitingMs += liveMs;
        slot.waitingSessions++;
      }
    }
  }
  // Convert per-REQ totals to seconds for the wire payload.
  const reqs = {};
  for (const [reqId, v] of Object.entries(byReq)) {
    reqs[reqId] = {
      totalSec: Math.floor(v.totalMs / 1000),
      waitingSec: Math.floor(v.waitingMs / 1000),
      waitingSessions: v.waitingSessions,
      turns: v.turns,
    };
  }
  return {
    totalSec: Math.floor(totalMs / 1000),
    waitingSec: Math.floor(waitingMs / 1000),
    waitingSessions,
    activeSessions,
    turns: totalTurns,
    byReq: reqs,
  };
}

function snapshotProject(root) {
  // Resolution order for the live state file (post-2026-06-07 contract):
  //
  //   Main checkout's spec dir is now the CANONICAL location of
  //   pipeline-state.json for the entire run — Phase 0 → Phase 8 — so it
  //   survives `git worktree remove` in Phase 8 cleanup. The dashboard
  //   prefers the main-checkout candidate whenever it has a state file.
  //
  //   Legacy fallback: pipelines started under the old contract still
  //   have their state file inside the worktree. We honor that as a
  //   secondary source — but the moment a main-checkout state appears,
  //   it wins. This prevents the "ghost REQ" failure mode where a
  //   worktree gets removed mid-run, the worktree state file vanishes,
  //   and the dashboard reverts the REQ to "spec only / yet to start".
  //
  //   Stickiness: once we've seen a stateful entry for a REQ, we never
  //   regress it to a stateless candidate (e.g., a fresh spec dir that
  //   appeared in main after the worktree was removed). The reconciler
  //   is the only path that should change a stateful → stateless
  //   transition, and it does so explicitly by writing a new file.
  const mainSpecs = listSpecDirs(root.path);
  const wtSpecs = listWorktreeSpecDirs(root.path);
  const byReq = new Map();
  // Pass 1: main checkout — canonical preference.
  for (const dir of mainSpecs) {
    const id = reqIdFromSpecDir(dir);
    const hasState = fs.existsSync(path.join(dir, 'pipeline-state.json'));
    byReq.set(id, { dir, hasState, source: 'main' });
  }
  // Pass 2: worktree — only fills slots where main had no state at all.
  // Critical: this NEVER overrides a main-checkout candidate that already
  // has state. Worktree state is only used as a legacy bridge.
  for (const dir of wtSpecs) {
    const id = reqIdFromSpecDir(dir);
    const hasState = fs.existsSync(path.join(dir, 'pipeline-state.json'));
    const existing = byReq.get(id);
    if (!existing) {
      byReq.set(id, { dir, hasState, source: 'worktree' });
      continue;
    }
    // Main candidate exists but has no state (Phase 0/1 not yet written,
    // or state was lost). Worktree's state file (if any) is a better
    // signal than empty — but DON'T regress a main-checkout candidate
    // that already has state.
    if (!existing.hasState && hasState) {
      byReq.set(id, { dir, hasState, source: 'worktree' });
    }
  }
  const reqs = [...byReq.values()].map((c) => projectReqState(c.dir, { rootPath: root.path })).filter(Boolean);
  reqs.sort((a, b) => a.reqId.localeCompare(b.reqId));
  return {
    name: root.name,
    path: root.path,
    exists: fs.existsSync(path.join(root.path, '.adlc')),
    reqs,
  };
}

function snapshot() {
  ingestUserWaitLog();
  const roots = readRegistry();
  // Cache per-session attribution once per snapshot. Cheap: each cache
  // entry is two prefix lookups + one regex against a short string.
  for (const s of userWaitBySession.values()) {
    s._rootCache = attributeToRoot(s.cwd, roots);
    s._reqCache = reqIdFromCwd(s.cwd);
  }
  const nowMs = Date.now();
  const projects = roots.map(snapshotProject)
    .filter((p) => p.exists)
    .map((p) => {
      const userWait = userWaitFor(p.path, nowMs);
      // Stitch per-REQ user-wait into each REQ entry. REQs with no
      // worktree-attributed sessions get a zero-valued shape so the UI
      // can render uniformly without null-checks.
      const reqs = p.reqs.map((r) => ({
        ...r,
        userWait: userWait.byReq[r.reqId] || {
          totalSec: 0, waitingSec: 0, waitingSessions: 0, turns: 0,
        },
      }));
      // Strip the byReq map from the project-level rollup so the wire
      // payload doesn't repeat the per-REQ data twice.
      const { byReq: _drop, ...projectRollup } = userWait;
      return { ...p, reqs, userWait: projectRollup };
    });
  projects.sort((a, b) => a.name.localeCompare(b.name));
  return {
    generatedAt: new Date().toISOString(),
    phaseLabels: PHASE_LABELS,
    projects,
  };
}

const clients = new Set();
let lastPayload = '';

function broadcast() {
  const snap = snapshot();
  const payload = JSON.stringify(snap);
  if (payload === lastPayload) return;
  lastPayload = payload;
  const frame = `event: state\ndata: ${payload}\n\n`;
  for (const res of clients) {
    try { res.write(frame); } catch (_) { /* drop */ }
  }
}

function startPolling() {
  setInterval(broadcast, POLL_MS).unref();
}

function serveStatic(res, file, contentType) {
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(500); res.end('Read error');
      return;
    }
    res.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-store' });
    res.end(data);
  });
}

const server = http.createServer((req, res) => {
  const url = (req.url || '/').split('?')[0];
  if (url === '/' || url === '/index.html') {
    serveStatic(res, HTML_PATH, 'text/html; charset=utf-8');
    return;
  }
  if (url === '/api/state') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(snapshot()));
    return;
  }
  if (url === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      ok: true,
      pid: process.pid,
      registry: REGISTRY_FILE,
      projects: readRegistry().length,
    }));
    return;
  }
  if (url === '/events') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-store',
      Connection: 'keep-alive',
    });
    res.write(`event: state\ndata: ${JSON.stringify(snapshot())}\n\n`);
    clients.add(res);
    req.on('close', () => clients.delete(res));
    return;
  }
  res.writeHead(404); res.end('Not found');
});

function shutdown() {
  for (const res of clients) { try { res.end(); } catch (_) {} }
  try { fs.unlinkSync(PID_FILE); } catch (_) {}
  try { fs.unlinkSync(PORT_FILE); } catch (_) {}
  try { fs.unlinkSync(URL_FILE); } catch (_) {}
  process.exit(0);
}

ensureHomeRuntime();

server.on('error', (err) => {
  log(`server error: ${err && err.message}`);
  process.exit(1);
});

server.listen(PORT, HOST, () => {
  fs.writeFileSync(PID_FILE, String(process.pid));
  fs.writeFileSync(PORT_FILE, String(PORT));
  fs.writeFileSync(URL_FILE, `http://${HOST}:${PORT}`);
  log(`listening on http://${HOST}:${PORT}`);
  startPolling();
});

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
