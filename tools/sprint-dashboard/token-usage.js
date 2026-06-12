'use strict';

// Token usage aggregator for the sprint dashboard.
//
// Reads Claude Code transcript JSONL files from
// `~/.claude/projects/<flattened-cwd>/*.jsonl`, extracts per-message
// `usage` blocks, and rolls them up to:
//   - per phase (0..8) for a REQ, by interleaving message timestamps
//     against `pipeline-state.json.phaseHistory[*]` windows + the live
//     in-flight phase span (`currentPhaseStartedAt → now`).
//   - per REQ totals (sum across phases).
//   - per project totals (sum across REQs).
//
// Attribution is by `sessionId`: the pipeline-runner records its own
// CLAUDE_SESSION_ID in `pipeline-state.json.sessionId` at Phase 0, and
// every message in that session's transcript carries the same id —
// including sidechain (sub-agent) messages spawned via the Agent tool.
//
// Caching: each transcript file is parsed only when (mtime, size) change
// since last seen. Re-aggregation across the same parsed messages is
// O(messages) per poll, which is comfortably under the 1.5s budget.

const fs = require('fs');
const path = require('path');
const os = require('os');

const HOME = os.homedir();

// Translate an absolute cwd to the flattened directory name Claude Code
// uses under ~/.claude/projects/. The CLI replaces every path separator
// with '-' and prepends a leading '-' (since the path is absolute).
//   /Users/me/Downloads/Workspaces/Foo  →  -Users-me-Downloads-Workspaces-Foo
// We test multiple candidate roots: the project root itself plus any
// worktree under <root>/.worktrees/* (each worktree is its own session
// cwd from Claude Code's perspective).
function projectKeyFromPath(absPath) {
  return absPath.replace(/\//g, '-');
}

function listTranscriptDirsForRoot(rootPath) {
  const dirs = [];
  const rootKey = projectKeyFromPath(rootPath);
  const rootDir = path.join(HOME, '.claude', 'projects', rootKey);
  if (fs.existsSync(rootDir)) dirs.push(rootDir);

  // Worktrees: each <root>/.worktrees/<name>/ also has its own
  // ~/.claude/projects/<key> directory when a Claude session ran there.
  const worktreesRoot = path.join(rootPath, '.worktrees');
  if (fs.existsSync(worktreesRoot)) {
    let entries;
    try { entries = fs.readdirSync(worktreesRoot); } catch (_) { entries = []; }
    for (const wt of entries) {
      const wtPath = path.join(worktreesRoot, wt);
      let stat;
      try { stat = fs.statSync(wtPath); } catch (_) { continue; }
      if (!stat.isDirectory()) continue;
      // Worktrees can be nested (e.g. .worktrees/feat/REQ-123-foo). Walk.
      walkForTranscriptDirs(wtPath, dirs);
    }
  }
  return dirs;
}

function walkForTranscriptDirs(absPath, out) {
  const key = projectKeyFromPath(absPath);
  const dir = path.join(HOME, '.claude', 'projects', key);
  if (fs.existsSync(dir)) out.push(dir);
  let entries;
  try { entries = fs.readdirSync(absPath); } catch (_) { return; }
  for (const e of entries) {
    if (e.startsWith('.')) continue;
    const child = path.join(absPath, e);
    let stat;
    try { stat = fs.statSync(child); } catch (_) { continue; }
    if (stat.isDirectory()) walkForTranscriptDirs(child, out);
  }
}

// Cache: file path → { mtimeMs, size, messages: [{tsMs, sessionId, usage}] }.
// Re-parse a file only when (mtime, size) change. On append-only growth
// (the common case during a live run) we re-parse the whole file —
// transcripts are typically a few MB and the parse cost is dwarfed by
// the time it takes Claude to actually generate the next message.
const transcriptCache = new Map();

function parseTranscript(filePath) {
  let stat;
  try { stat = fs.statSync(filePath); } catch (_) { return null; }
  const cached = transcriptCache.get(filePath);
  if (cached && cached.mtimeMs === stat.mtimeMs && cached.size === stat.size) {
    return cached.messages;
  }
  let txt;
  try { txt = fs.readFileSync(filePath, 'utf8'); } catch (_) { return null; }
  const messages = [];
  for (const line of txt.split('\n')) {
    if (!line) continue;
    let obj;
    try { obj = JSON.parse(line); } catch (_) { continue; }
    if (!obj || obj.type !== 'assistant') continue;
    const m = obj.message;
    if (!m || !m.usage) continue;
    const tsMs = Date.parse(obj.timestamp);
    if (!Number.isFinite(tsMs)) continue;
    const sessionId = typeof obj.sessionId === 'string' ? obj.sessionId : null;
    if (!sessionId) continue;
    const u = m.usage;
    // Dedupe note: a tool_use turn often appears twice in the JSONL
    // (once per tool result echo). The same `message.id` is emitted
    // both times with identical `usage`. Key dedupe on message.id.
    messages.push({
      id: m.id || null,
      tsMs,
      sessionId,
      usage: {
        input: Number(u.input_tokens) || 0,
        output: Number(u.output_tokens) || 0,
        cacheCreate: Number(u.cache_creation_input_tokens) || 0,
        cacheRead: Number(u.cache_read_input_tokens) || 0,
      },
      model: m.model || null,
    });
  }
  transcriptCache.set(filePath, { mtimeMs: stat.mtimeMs, size: stat.size, messages });
  return messages;
}

// Collect every transcript message for a given (rootPath, sessionId).
// Iterates all transcript dirs that could host this session — the root
// plus its worktrees. Dedupes by message.id (per-session-id) since the
// same message can appear in multiple JSONLs when a session is resumed.
function messagesForSession(rootPath, sessionId) {
  const dirs = listTranscriptDirsForRoot(rootPath);
  const seenIds = new Set();
  const out = [];
  for (const dir of dirs) {
    let files;
    try { files = fs.readdirSync(dir); } catch (_) { continue; }
    for (const f of files) {
      if (!f.endsWith('.jsonl')) continue;
      const filePath = path.join(dir, f);
      const msgs = parseTranscript(filePath);
      if (!msgs) continue;
      for (const m of msgs) {
        if (m.sessionId !== sessionId) continue;
        const key = m.id || `${m.tsMs}::${m.usage.input}::${m.usage.output}`;
        if (seenIds.has(key)) continue;
        seenIds.add(key);
        out.push(m);
      }
    }
  }
  return out;
}

function emptyBucket() {
  return { input: 0, output: 0, cacheCreate: 0, cacheRead: 0, messages: 0 };
}

function addUsage(bucket, u) {
  bucket.input += u.input;
  bucket.output += u.output;
  bucket.cacheCreate += u.cacheCreate;
  bucket.cacheRead += u.cacheRead;
  bucket.messages += 1;
}

// Build phase windows from a REQ's pipeline-state-shaped object. Each
// completed phase is a [startedAt, completedAt] interval; the in-flight
// phase (currentPhase) extends from currentPhaseStartedAt to now.
//
// Returns: array of { phase, startMs, endMs }. Sorted by startMs so a
// linear scan over messages can advance through windows in O(M+W).
function buildPhaseWindows(req, nowMs) {
  const windows = [];
  const history = Array.isArray(req.phaseHistory) ? req.phaseHistory : [];
  for (const p of history) {
    if (!p) continue;
    const phase = phaseIndexOf(p.phase);
    const a = Date.parse(p.startedAt);
    const b = Date.parse(p.completedAt);
    if (phase === null || !Number.isFinite(a) || !Number.isFinite(b) || b < a) continue;
    windows.push({ phase, startMs: a, endMs: b });
  }
  if (typeof req.currentPhase === 'number' && typeof req.currentPhaseStartedAt === 'string') {
    const a = Date.parse(req.currentPhaseStartedAt);
    if (Number.isFinite(a)) {
      windows.push({ phase: req.currentPhase, startMs: a, endMs: nowMs });
    }
  }
  windows.sort((x, y) => x.startMs - y.startMs);
  return windows;
}

function phaseIndexOf(v) {
  if (Number.isInteger(v)) return v;
  if (typeof v === 'string') {
    const m = v.match(/(\d+)/);
    if (m) return Number(m[1]);
  }
  return null;
}

// Aggregate usage for one REQ. Requires the raw state object so we can
// read phaseHistory and currentPhaseStartedAt — projectReqState's
// massaged output drops some of those fields. Caller passes the raw
// state plus the resolved sessionId (or null).
function aggregateForReq(rootPath, rawState, nowMs) {
  const sessionId = rawState && typeof rawState.sessionId === 'string'
    ? rawState.sessionId : null;
  if (!sessionId) {
    return { hasSessionId: false, total: emptyBucket(), byPhase: {} };
  }
  const messages = messagesForSession(rootPath, sessionId);
  const windows = buildPhaseWindows(rawState, nowMs);
  // REQ outer window: a single Claude session may run multiple REQs (e.g.
  // /spec on REQ-A then /proceed on REQ-B). Filter messages to this REQ's
  // own time span before bucketing — otherwise sibling REQs that share
  // the sessionId would each claim the entire session's tokens.
  // Outer window = [min(window.start, state.startedAt), max(window.end, state.lastActivity, now-if-live)].
  // Add a small grace pad on each side to catch messages straddling boundaries.
  const PAD_MS = 60 * 1000;
  let outerStart = Infinity, outerEnd = -Infinity;
  for (const w of windows) {
    if (w.startMs < outerStart) outerStart = w.startMs;
    if (w.endMs > outerEnd) outerEnd = w.endMs;
  }
  if (rawState.startedAt) {
    const s = Date.parse(rawState.startedAt);
    if (Number.isFinite(s) && s < outerStart) outerStart = s;
  }
  // If the REQ has no windows at all (no phaseHistory, no currentPhase),
  // skip the outer-window filter — there's no meaningful gate.
  const hasOuterWindow = Number.isFinite(outerStart) && Number.isFinite(outerEnd);
  const byPhase = {};
  const total = emptyBucket();
  for (const m of messages) {
    if (hasOuterWindow && (m.tsMs < outerStart - PAD_MS || m.tsMs > outerEnd + PAD_MS)) {
      continue; // belongs to a different REQ that shared this sessionId
    }
    addUsage(total, m.usage);
    // Find the latest window whose start <= m.tsMs and end >= m.tsMs.
    // For simplicity we accept the first matching window (windows
    // generally don't overlap in a healthy run).
    let phase = null;
    for (const w of windows) {
      if (m.tsMs >= w.startMs && m.tsMs <= w.endMs) { phase = w.phase; break; }
    }
    // Fallback: bucket pre-Phase-0 / post-completion stragglers under
    // the nearest phase by start time, so the UI never shows "lost"
    // tokens that don't add up to total.
    if (phase === null && windows.length) {
      let nearest = windows[0];
      let nearestDist = Math.abs(m.tsMs - nearest.startMs);
      for (const w of windows) {
        const d = Math.min(Math.abs(m.tsMs - w.startMs), Math.abs(m.tsMs - w.endMs));
        if (d < nearestDist) { nearest = w; nearestDist = d; }
      }
      phase = nearest.phase;
    }
    if (phase === null) phase = 0;
    if (!byPhase[phase]) byPhase[phase] = emptyBucket();
    addUsage(byPhase[phase], m.usage);
  }
  return { hasSessionId: true, total, byPhase };
}

function sumBuckets(buckets) {
  const out = emptyBucket();
  for (const b of buckets) {
    out.input += b.input;
    out.output += b.output;
    out.cacheCreate += b.cacheCreate;
    out.cacheRead += b.cacheRead;
    out.messages += b.messages;
  }
  return out;
}

module.exports = {
  aggregateForReq,
  sumBuckets,
  emptyBucket,
};
