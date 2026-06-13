#!/usr/bin/env node
'use strict';

// Git-committed metrics snapshot generator.
//
// Reads .adlc/specs/<REQ>/pipeline-state.json (the same source the live
// sprint-dashboard uses) plus per-REQ token totals from local Claude
// transcripts (via tools/sprint-dashboard/token-usage.js), then writes:
//
//   .adlc/metrics/<REQ>.json   per-REQ snapshot (stable shape; commit-safe)
//   .adlc/metrics/index.json   rolled-up array used by dashboard.html
//   .adlc/metrics/dashboard.html
//                              regenerated from the template with index.json
//                              embedded inline so it works on file:// without
//                              a server.
//
// Token totals are best-effort: they require the local transcript files
// that lived on the machine where the REQ was run. If transcripts are
// missing (e.g. a teammate cloning the repo, or backfill of an old REQ
// whose session aged out), we still write the snapshot — just with
// tokens.captured = false so the dashboard can show "—" for that row.
//
// Usage:
//   node tools/git-dashboard/snapshot.js --req REQ-258
//   node tools/git-dashboard/snapshot.js --all
//   node tools/git-dashboard/snapshot.js --req REQ-258 --root /abs/path/to/repo

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const tokens = require('../sprint-dashboard/token-usage.js');

function parseArgs(argv) {
  const out = {
    req: null, all: false, root: null,
    commit: false, milestone: null, push: true,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--all') out.all = true;
    else if (a === '--req') out.req = argv[++i];
    else if (a === '--root') out.root = argv[++i];
    else if (a === '--commit') out.commit = true;
    else if (a === '--milestone') out.milestone = argv[++i];
    else if (a === '--no-push') out.push = false;
    else if (a === '--help' || a === '-h') {
      process.stdout.write(
        'Usage: snapshot.js [--req REQ-XXX | --all] [--root /abs/path]\n' +
        '                  [--commit [--milestone <label>] [--no-push]]\n\n' +
        '  --commit    after writing snapshot, fetch+rebase main, commit metrics, push.\n' +
        '              Non-fatal — failures log and exit 0 so the caller (proceed/sprint)\n' +
        '              never gets blocked on a metrics push.\n' +
        '  --milestone label embedded in the commit message (e.g. "phase-0-started").\n' +
        '  --no-push   commit locally but do not push (useful for testing).\n'
      );
      process.exit(0);
    }
  }
  if (!out.all && !out.req) {
    process.stderr.write('snapshot: pass --req REQ-XXX or --all\n');
    process.exit(2);
  }
  return out;
}

function git(root, args, opts = {}) {
  const r = spawnSync('git', ['-C', root, ...args], {
    encoding: 'utf8', ...opts,
  });
  return {
    code: r.status == null ? -1 : r.status,
    stdout: (r.stdout || '').trim(),
    stderr: (r.stderr || '').trim(),
  };
}

function logWarn(msg) { process.stderr.write(`snapshot: ${msg}\n`); }
function logInfo(msg) { process.stdout.write(`snapshot: ${msg}\n`); }

function findRoot(startDir) {
  let dir = path.resolve(startDir);
  while (dir !== path.dirname(dir)) {
    if (fs.existsSync(path.join(dir, '.adlc'))) return dir;
    dir = path.dirname(dir);
  }
  return null;
}

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (_) { return null; }
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

// .adlc/specs/<REQ-id-slug>/ — find the spec dir for a given REQ id.
function specDirsUnder(root) {
  const dir = path.join(root, '.adlc', 'specs');
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .map((name) => ({ name, abs: path.join(dir, name) }))
    .filter((e) => fs.statSync(e.abs).isDirectory());
}

function reqIdFromName(name) {
  // Match leading REQ-NNN or PFX-REQ-NNN (e.g. SAP-REQ-002).
  const m = name.match(/^([A-Z]+-)?REQ-\d+/);
  return m ? m[0] : null;
}

function findSpecDirByReq(root, reqId) {
  for (const e of specDirsUnder(root)) {
    if (reqIdFromName(e.name) === reqId) return e.abs;
  }
  return null;
}

// Pull a status string out of requirement.md frontmatter without a YAML lib.
function readReqStatus(specDir) {
  const file = path.join(specDir, 'requirement.md');
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf8');
  const fm = txt.match(/^---\n([\s\S]*?)\n---/);
  if (!fm) return null;
  const m = fm[1].match(/^status:\s*(.+)$/m);
  return m ? m[1].trim().replace(/^"|"$/g, '') : null;
}

function readReqTitle(specDir) {
  const file = path.join(specDir, 'requirement.md');
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf8');
  const fm = txt.match(/^---\n([\s\S]*?)\n---/);
  if (!fm) return null;
  const m = fm[1].match(/^title:\s*"?([^"\n]+)"?$/m);
  return m ? m[1].trim() : null;
}

function countTasks(specDir) {
  const dir = path.join(specDir, 'tasks');
  if (!fs.existsSync(dir)) return { total: 0, complete: 0 };
  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.md'));
  let complete = 0;
  for (const f of files) {
    const txt = fs.readFileSync(path.join(dir, f), 'utf8');
    const fm = txt.match(/^---\n([\s\S]*?)\n---/);
    if (!fm) continue;
    const m = fm[1].match(/^status:\s*(\S+)/m);
    if (m && /^complete\b/i.test(m[1])) complete++;
  }
  return { total: files.length, complete };
}

function buildSnapshot(root, specDirAbs) {
  const specName = path.basename(specDirAbs);
  const reqId = reqIdFromName(specName);
  const stateFile = path.join(specDirAbs, 'pipeline-state.json');
  const state = readJson(stateFile);
  const reqStatus = readReqStatus(specDirAbs);
  const title = readReqTitle(specDirAbs);
  const taskCounts = countTasks(specDirAbs);

  // Token aggregation from local transcripts (best-effort).
  let tokenBlock = { captured: false };
  if (state && state.sessionId) {
    const agg = tokens.aggregateForReq(root, state, Date.now());
    if (agg.hasSessionId && agg.total.messages > 0) {
      tokenBlock = {
        captured: true,
        sessionId: state.sessionId,
        total: agg.total,
        byPhase: agg.byPhase,
      };
    } else if (agg.hasSessionId) {
      tokenBlock = { captured: false, sessionId: state.sessionId, reason: 'no-transcript-messages-found' };
    }
  } else if (state) {
    tokenBlock = { captured: false, reason: 'no-sessionId-in-pipeline-state' };
  } else {
    tokenBlock = { captured: false, reason: 'no-pipeline-state' };
  }

  // Repos / PR / merge — keep one canonical set of fields the static
  // dashboard can render without re-walking pipeline-state.
  let repos = [];
  if (state && state.repos && typeof state.repos === 'object') {
    for (const [id, r] of Object.entries(state.repos)) {
      if (!r) continue;
      repos.push({
        id,
        primary: !!r.primary,
        prUrl: r.prUrl || null,
        merged: !!r.merged,
        mergedAt: r.mergedAt || null,
        mergeCommit: r.mergeCommit || null,
        branch: r.branch || null,
      });
    }
  }

  return {
    schemaVersion: 1,
    req: reqId,
    specSlug: specName,
    title,
    requirementStatus: reqStatus,
    tasks: taskCounts,
    pipeline: state ? {
      completed: !!state.completed,
      terminalState: state.terminalState || null,
      currentPhase: typeof state.currentPhase === 'number' ? state.currentPhase : null,
      completedPhases: Array.isArray(state.completedPhases) ? state.completedPhases : [],
      startedAt: state.startedAt || null,
      complexity: state.complexity || null,
      // Phase durations: easy to read off phaseHistory; useful for the
      // dashboard's per-phase bar without re-parsing the raw state.
      phaseHistory: Array.isArray(state.phaseHistory) ? state.phaseHistory.map((p) => ({
        phase: p.phase, name: p.name || null,
        startedAt: p.startedAt || null,
        completedAt: p.completedAt || null,
      })) : [],
    } : null,
    repos,
    tokens: tokenBlock,
    // Snapshot generation is deliberately stable — capturedAt comes from
    // the input file mtimes so re-running the tool with no upstream
    // changes produces a no-op (no churning git diff).
    sourceMtimes: {
      pipelineState: state ? safeMtimeIso(stateFile) : null,
      requirement: safeMtimeIso(path.join(specDirAbs, 'requirement.md')),
    },
  };
}

function safeMtimeIso(file) {
  try {
    const s = fs.statSync(file);
    return new Date(s.mtimeMs).toISOString();
  } catch (_) { return null; }
}

function rebuildIndex(metricsDir) {
  const out = [];
  for (const f of fs.readdirSync(metricsDir)) {
    if (!f.endsWith('.json') || f === 'index.json') continue;
    const data = readJson(path.join(metricsDir, f));
    if (!data || !data.req) continue;
    out.push(summarizeForIndex(data));
  }
  out.sort((a, b) => {
    // Order: in-flight first, then merged-newest, then by REQ id.
    const an = !a.merged ? 0 : 1;
    const bn = !b.merged ? 0 : 1;
    if (an !== bn) return an - bn;
    const am = a.mergedAt || '';
    const bm = b.mergedAt || '';
    if (am !== bm) return bm.localeCompare(am);
    return a.req.localeCompare(b.req);
  });
  fs.writeFileSync(
    path.join(metricsDir, 'index.json'),
    JSON.stringify({ schemaVersion: 1, generatedAt: stableGeneratedAt(out), reqs: out }, null, 2) + '\n'
  );
  return out;
}

// generatedAt is the latest source mtime across all REQs — keeps repeated
// runs idempotent when nothing has changed.
function stableGeneratedAt(reqs) {
  let latest = '';
  for (const r of reqs) {
    if (r.lastUpdatedAt && r.lastUpdatedAt > latest) latest = r.lastUpdatedAt;
  }
  return latest || null;
}

function summarizeForIndex(data) {
  const primary = (data.repos || []).find((r) => r.primary) || (data.repos || [])[0] || null;
  const phaseHistory = data.pipeline?.phaseHistory || [];
  const startedAt = data.pipeline?.startedAt || null;
  const lastEnded = phaseHistory
    .map((p) => p.completedAt)
    .filter(Boolean)
    .sort()
    .slice(-1)[0] || null;
  const lastUpdatedAt = [
    data.sourceMtimes?.pipelineState,
    data.sourceMtimes?.requirement,
    lastEnded,
  ].filter(Boolean).sort().slice(-1)[0] || null;

  return {
    req: data.req,
    title: data.title || null,
    requirementStatus: data.requirementStatus || null,
    completed: !!data.pipeline?.completed,
    terminalState: data.pipeline?.terminalState || null,
    currentPhase: data.pipeline?.currentPhase ?? null,
    completedPhases: data.pipeline?.completedPhases || [],
    complexity: data.pipeline?.complexity || null,
    tasks: data.tasks || { total: 0, complete: 0 },
    startedAt,
    lastUpdatedAt,
    merged: !!primary?.merged,
    mergedAt: primary?.mergedAt || null,
    prUrl: primary?.prUrl || null,
    repoCount: (data.repos || []).length,
    tokens: data.tokens?.captured ? {
      captured: true,
      input: data.tokens.total.input,
      output: data.tokens.total.output,
      cacheCreate: data.tokens.total.cacheCreate,
      cacheRead: data.tokens.total.cacheRead,
      messages: data.tokens.total.messages,
      byPhase: data.tokens.byPhase,
    } : { captured: false, reason: data.tokens?.reason || 'unknown' },
  };
}

function rebuildDashboard(metricsDir, indexPayload) {
  const tplPath = path.join(__dirname, 'dashboard.template.html');
  if (!fs.existsSync(tplPath)) {
    process.stderr.write(`snapshot: dashboard.template.html missing at ${tplPath} — skipping HTML\n`);
    return;
  }
  const tpl = fs.readFileSync(tplPath, 'utf8');
  // Replace the inline data island. The placeholder is a script tag whose
  // body is exactly this token; everything else in the template stays
  // verbatim so /wrapup commits diff cleanly when only data changes.
  const out = tpl.replace(
    /(<script id="adlc-metrics-data" type="application\/json">)[\s\S]*?(<\/script>)/,
    `$1\n${JSON.stringify(indexPayload, null, 2)}\n$2`
  );
  fs.writeFileSync(path.join(metricsDir, 'dashboard.html'), out);
}

function snapshotOne(root, reqId) {
  const specDir = findSpecDirByReq(root, reqId);
  if (!specDir) {
    process.stderr.write(`snapshot: no spec dir for ${reqId}\n`);
    return null;
  }
  const data = buildSnapshot(root, specDir);
  const metricsDir = path.join(root, '.adlc', 'metrics');
  ensureDir(metricsDir);
  const outFile = path.join(metricsDir, `${reqId}.json`);
  fs.writeFileSync(outFile, JSON.stringify(data, null, 2) + '\n');
  return { reqId, file: outFile };
}

function snapshotAll(root) {
  const results = [];
  for (const e of specDirsUnder(root)) {
    const reqId = reqIdFromName(e.name);
    if (!reqId) continue;
    const r = snapshotOne(root, reqId);
    if (r) results.push(r);
  }
  return results;
}

// Cooperative lock so concurrent /sprint pipelines that both want to push
// metrics don't race on the same `git pull --rebase` + `git push`. Same
// mkdir-based pattern used by the LESSON/ASSUME counters elsewhere in
// the toolkit (LESSON-014 / LESSON-110). Non-blocking: if we can't grab
// the lock in 30s, give up and let the next milestone push catch up.
function withLock(root, fn) {
  const lockDir = path.join(root, '.adlc', 'metrics', '.commit.lock.d');
  ensureDir(path.join(root, '.adlc', 'metrics'));
  // Symlink pre-check (LESSON-014) — if someone has swapped the lock for a
  // symlink, refuse to operate on it.
  try {
    const st = fs.lstatSync(lockDir);
    if (st.isSymbolicLink()) {
      logWarn(`refusing: ${lockDir} is a symlink`);
      return null;
    }
  } catch (_) { /* not present — fine */ }
  let acquired = false;
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      fs.mkdirSync(lockDir);
      acquired = true;
      break;
    } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      // brief backoff
      const wait = 200 + Math.floor(Math.random() * 200);
      const end = Date.now() + wait;
      while (Date.now() < end) { /* spin briefly — keep deps zero */ }
    }
  }
  if (!acquired) {
    logWarn('could not acquire metrics commit lock in 30s — skipping commit');
    return null;
  }
  try {
    return fn();
  } finally {
    try { fs.rmdirSync(lockDir); } catch (_) { /* best effort */ }
  }
}

// Commit + push the metrics directory. Designed to be called from
// /proceed and /wrapup hooks. Every failure path is non-fatal — the
// caller never gets a non-zero exit code from --commit. We print a
// warning and return so the main pipeline keeps moving.
function commitAndPush(root, reqId, milestone, doPush) {
  // Refuse to commit if the working tree at `root` isn't on a main-class
  // branch. The caller is expected to pass --root pointing at the main
  // checkout (this matches /wrapup's <ARTIFACT_ROOT> resolution).
  const branchRes = git(root, ['rev-parse', '--abbrev-ref', 'HEAD']);
  if (branchRes.code !== 0) {
    logWarn(`not a git repo at ${root} — skipping commit`);
    return;
  }
  const branch = branchRes.stdout;
  if (branch !== 'main' && branch !== 'master') {
    logWarn(`current branch is ${branch}, not main/master — skipping commit. Pass --root pointing at main checkout.`);
    return;
  }

  // Fetch + rebase first so any metrics another runner pushed (their
  // per-REQ JSON) lands on disk, and we regenerate the aggregate from
  // the union. `git pull --rebase` is safe here: if there are local
  // unstaged changes outside .adlc/metrics it will refuse and we'll bail.
  const fetchRes = git(root, ['fetch', 'origin', branch]);
  if (fetchRes.code !== 0) {
    logWarn(`git fetch failed — skipping push: ${fetchRes.stderr}`);
    return;
  }
  // Only rebase if remote moved — avoids unnecessary churn.
  const behindRes = git(root, ['rev-list', '--count', `HEAD..origin/${branch}`]);
  const behind = Number(behindRes.stdout) || 0;
  if (behind > 0) {
    // We need a clean working tree outside .adlc/metrics for rebase. If
    // there are unstaged changes, stash them, rebase, pop. Use a unique
    // stash name so concurrent runs don't pop each other's stash.
    const dirty = git(root, ['status', '--porcelain']);
    const dirtyOutsideMetrics = dirty.stdout.split('\n')
      .filter((l) => l && !l.includes('.adlc/metrics/'));
    let stashed = false;
    if (dirtyOutsideMetrics.length) {
      const stashName = `adlc-metrics-${Date.now()}-${process.pid}`;
      const stashRes = git(root, ['stash', 'push', '--include-untracked', '-m', stashName]);
      if (stashRes.code !== 0) {
        logWarn(`git stash failed — skipping push: ${stashRes.stderr}`);
        return;
      }
      stashed = true;
    }
    const rebaseRes = git(root, ['pull', '--rebase', 'origin', branch]);
    if (rebaseRes.code !== 0) {
      logWarn(`git pull --rebase failed — skipping push: ${rebaseRes.stderr}`);
      git(root, ['rebase', '--abort']);
      if (stashed) git(root, ['stash', 'pop']);
      return;
    }
    if (stashed) {
      const popRes = git(root, ['stash', 'pop']);
      if (popRes.code !== 0) {
        logWarn(`stash pop failed after rebase — caller must resolve. stash kept.`);
        // Don't push — the working tree is in an unexpected state.
        return;
      }
    }
    // After rebase, regenerate aggregates because new per-REQ files may
    // have arrived from origin during the pull.
    const metricsDir = path.join(root, '.adlc', 'metrics');
    rebuildIndex(metricsDir);
    const indexPayload = readJson(path.join(metricsDir, 'index.json'));
    rebuildDashboard(metricsDir, indexPayload);
  }

  // Stage ONLY the metrics dir — never blanket-add (LESSON-110 from /wrapup).
  const addRes = git(root, ['add', '.adlc/metrics/']);
  if (addRes.code !== 0) {
    logWarn(`git add failed: ${addRes.stderr}`);
    return;
  }
  // Anything actually staged?
  const diffRes = git(root, ['diff', '--cached', '--quiet', '--', '.adlc/metrics/']);
  if (diffRes.code === 0) {
    logInfo('no metrics changes to commit');
    return;
  }
  const subject = milestone
    ? `chore(${reqId}): metrics snapshot — ${milestone}`
    : `chore(${reqId}): metrics snapshot`;
  const commitRes = git(root, [
    'commit',
    '-m', subject,
    '-m', 'Auto-generated by tools/git-dashboard/snapshot.js. Updates the static\n' +
          'git-committed dashboard at .adlc/metrics/dashboard.html so teammates\n' +
          'see in-flight REQ status without running the live sprint dashboard.',
    '--', '.adlc/metrics/',
  ]);
  if (commitRes.code !== 0) {
    logWarn(`git commit failed: ${commitRes.stderr}`);
    return;
  }
  if (!doPush) {
    logInfo(`committed locally (--no-push): ${subject}`);
    return;
  }
  const pushRes = git(root, ['push', 'origin', branch]);
  if (pushRes.code !== 0) {
    logWarn(`git push failed (commit landed locally): ${pushRes.stderr}`);
    return;
  }
  logInfo(`pushed: ${subject}`);
}

function main() {
  const args = parseArgs(process.argv);
  const root = args.root || findRoot(process.cwd());
  if (!root) {
    process.stderr.write('snapshot: could not locate .adlc/ — pass --root\n');
    process.exit(2);
  }
  let written;
  if (args.all) written = snapshotAll(root);
  else {
    const r = snapshotOne(root, args.req);
    written = r ? [r] : [];
  }
  if (!written.length) {
    process.stderr.write('snapshot: nothing written\n');
    process.exit(1);
  }
  const metricsDir = path.join(root, '.adlc', 'metrics');
  const indexReqs = rebuildIndex(metricsDir);
  const indexPayload = readJson(path.join(metricsDir, 'index.json'));
  rebuildDashboard(metricsDir, indexPayload);
  process.stdout.write(
    `snapshot: wrote ${written.length} per-REQ snapshot(s); index has ${indexReqs.length} REQ(s)\n`
  );

  if (args.commit) {
    // Commit + push under the cooperative lock so concurrent /sprint
    // pipelines serialize on this critical section. Only meaningful
    // when --req was passed (we know which REQ to label the commit
    // with) — for --all we still commit but with a generic message.
    const reqLabel = args.req || 'all';
    withLock(root, () => commitAndPush(root, reqLabel, args.milestone, args.push));
  }
}

main();
