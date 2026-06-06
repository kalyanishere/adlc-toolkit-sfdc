#!/usr/bin/env node
// ADLC sprint dashboard — zero-dep multi-project SSE server.
// Reads ~/.adlc/dashboard-registry.json on every poll and aggregates
// .adlc/specs/REQ-*/ across every registered project root.
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

function listSpecDirs(root) {
  const specsRoot = path.join(root, '.adlc', 'specs');
  if (!fs.existsSync(specsRoot)) return [];
  let entries;
  try { entries = fs.readdirSync(specsRoot); } catch (_) { return []; }
  return entries
    .filter((name) => /^REQ-/.test(name))
    .map((name) => path.join(specsRoot, name));
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
  const id = path.basename(specDir).match(/^(REQ-\d+)/);
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
    lastPhase: Array.isArray(state.phaseHistory) && state.phaseHistory.length
      ? state.phaseHistory[state.phaseHistory.length - 1]
      : null,
    startedAt: state.startedAt || null,
    integrationBranch: state.integrationBranch || null,
    repos,
    tasks,
  };
}

function snapshotProject(root) {
  const dirs = listSpecDirs(root.path);
  const reqs = dirs.map(projectReqState).filter(Boolean);
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
