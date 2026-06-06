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

const PORT = parseInt(process.env.ADLC_DASHBOARD_PORT || '5174', 10);
const HOST = '127.0.0.1';
const POLL_MS = 1500;

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
    const idMatch = f.match(/^(TASK-\d+)/);
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

function projectReqState(specDir) {
  const id = path.basename(specDir).match(/^((?:[A-Z]+-)?REQ-\d+)/);
  const reqId = id ? id[1] : path.basename(specDir);
  const stateFile = path.join(specDir, 'pipeline-state.json');
  const state = readJsonSafe(stateFile);

  const title = readReqTitle(specDir);
  const tasks = readTaskStrip(specDir);

  if (!state) {
    return {
      reqId,
      title,
      hasState: false,
      currentPhase: null,
      completed: false,
      blockers: [],
      currentTask: null,
      failedTasks: [],
      completedTasks: [],
      completedPhases: [],
      lastPhase: null,
      startedAt: null,
      lastActivityAt: null,
      currentPhaseStartedAt: null,
      activeMs: 0,
      hasPhaseTelemetry: false,
      integrationBranch: null,
      repos: {},
      tasks,
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

  return {
    reqId,
    title,
    hasState: true,
    currentPhase: state.currentPhase ?? null,
    completed: !!state.completed,
    blockers: Array.isArray(state.blockers) ? state.blockers : [],
    currentTask: state.phase4?.currentTask || null,
    failedTasks: Array.isArray(state.phase4?.failedTasks) ? state.phase4.failedTasks : [],
    completedTasks: Array.isArray(state.phase4?.completedTasks) ? state.phase4.completedTasks : [],
    completedPhases: Array.isArray(state.completedPhases) ? state.completedPhases : [],
    lastPhase: phaseHistory.length ? phaseHistory[phaseHistory.length - 1] : null,
    startedAt: state.startedAt || null,
    lastActivityAt,
    currentPhaseStartedAt,
    activeMs,
    hasPhaseTelemetry,
    integrationBranch: state.integrationBranch || null,
    repos,
    tasks,
  };
}

function snapshotProject(root) {
  // Collect spec dirs from both the main checkout (post-merge state files)
  // and every active worktree (in-flight state files written by /proceed
  // Step 0). Dedupe by REQ id, preferring the candidate that has a
  // pipeline-state.json — that's the live one. If neither has state, the
  // merged-checkout copy wins (it's the canonical resting place once a
  // pipeline finishes and worktrees are removed).
  const candidates = [
    ...listSpecDirs(root.path),
    ...listWorktreeSpecDirs(root.path),
  ];
  const byReq = new Map();
  for (const dir of candidates) {
    const id = reqIdFromSpecDir(dir);
    const hasState = fs.existsSync(path.join(dir, 'pipeline-state.json'));
    const existing = byReq.get(id);
    if (!existing) {
      byReq.set(id, { dir, hasState });
      continue;
    }
    // Prefer whichever candidate carries a state file. If both do (shouldn't
    // normally happen — would mean a merged spec with the worktree still
    // around), prefer the worktree (in-flight wins; the candidate list
    // appends worktrees after main, so the latter overwrites).
    if (hasState && !existing.hasState) byReq.set(id, { dir, hasState });
    else if (hasState && existing.hasState) byReq.set(id, { dir, hasState });
  }
  const reqs = [...byReq.values()].map((c) => projectReqState(c.dir)).filter(Boolean);
  reqs.sort((a, b) => a.reqId.localeCompare(b.reqId));
  return {
    name: root.name,
    path: root.path,
    exists: fs.existsSync(path.join(root.path, '.adlc')),
    reqs,
  };
}

function snapshot() {
  const roots = readRegistry();
  const projects = roots.map(snapshotProject)
    .filter((p) => p.exists);
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
