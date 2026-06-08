#!/usr/bin/env node
// Permission-set policy pre-flight.
//
// Framework policy: permission sets grant access at the OBJECT level using
// <objectPermissions> with viewAllFields=true (and editAllFields=true when
// allowEdit=true). They MUST NOT contain any <fieldPermissions> blocks.
//
// Per-field FLS in PermissionSet XML is the #1 cause of deploy failures
// (required / formula / master-detail / auto-number / compound / system
// fields are FLS-ineligible and reject deploy). Restrict access via
// separate permission sets, sharing, or encryption — never via
// <fieldPermissions>.
//
// This script BLOCKS when:
//   - any <fieldPermissions> block is present
//   - any <objectPermissions> block is missing <viewAllFields>true
//     (or missing <editAllFields>true when allowEdit=true)
//   - <userPermissions> grants ViewAllData or ModifyAllData
//   - (online mode) any object referenced in <objectPermissions> doesn't
//     exist in the target org
//
// Usage:
//   node tools/sf-preflight/check-permsets.mjs \
//     --workspace force-app \
//     --target-org <alias> \
//     [--cache-dir .adlc/.cache] \
//     [--offline]                 # parse only — skip the org existence check
//     [--json]                    # emit machine-readable findings
//
// Exit codes:
//   0 — no findings
//   1 — at least one finding (BLOCK)
//   2 — invocation error (bad args, missing org, etc.)

import { readFileSync, readdirSync, statSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join } from "node:path";

// --- arg parsing ----------------------------------------------------------

const args = process.argv.slice(2);
const opts = {
  workspace: "force-app",
  targetOrg: null,
  cacheDir: ".adlc/.cache",
  offline: false,
  json: false,
};
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === "--workspace") opts.workspace = args[++i];
  else if (a === "--target-org") opts.targetOrg = args[++i];
  else if (a === "--cache-dir") opts.cacheDir = args[++i];
  else if (a === "--offline") opts.offline = true;
  else if (a === "--json") opts.json = true;
  else if (a === "-h" || a === "--help") {
    console.log("Usage: check-permsets.mjs --workspace <dir> --target-org <alias> [--offline] [--json]");
    process.exit(0);
  } else {
    console.error(`Unknown argument: ${a}`);
    process.exit(2);
  }
}

if (!opts.offline && !opts.targetOrg) {
  console.error("ERROR: --target-org is required unless --offline is passed.");
  process.exit(2);
}
if (!existsSync(opts.workspace)) {
  console.error(`ERROR: workspace ${opts.workspace} does not exist`);
  process.exit(2);
}

// --- discover permission-set XML files -----------------------------------

function findPermSets(dir) {
  const out = [];
  const queue = [dir];
  while (queue.length) {
    const d = queue.pop();
    let entries;
    try { entries = readdirSync(d); } catch { continue; }
    for (const e of entries) {
      const p = join(d, e);
      let st;
      try { st = statSync(p); } catch { continue; }
      if (st.isDirectory()) queue.push(p);
      else if (e.endsWith(".permissionset-meta.xml")) out.push(p);
    }
  }
  return out;
}

const permSetFiles = findPermSets(opts.workspace);
if (permSetFiles.length === 0) {
  if (!opts.json) console.log("No permission sets found — nothing to check.");
  process.exit(0);
}

// --- block-level parsers --------------------------------------------------
// Tag-based parsing — avoids pulling a heavy XML dependency. Salesforce
// metadata is line-oriented and consistent.

function indexOfWithLine(xml, idx) {
  // 1-based line number for an offset in the source.
  let line = 1;
  for (let i = 0; i < idx && i < xml.length; i++) if (xml.charCodeAt(i) === 10) line++;
  return line;
}

function parseFieldPermissions(xml) {
  const blocks = [];
  const re = /<fieldPermissions>([\s\S]*?)<\/fieldPermissions>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    const body = m[1];
    const get = (tag) => {
      const t = new RegExp(`<${tag}>([^<]*)<\\/${tag}>`).exec(body);
      return t ? t[1].trim() : null;
    };
    blocks.push({
      field: get("field"),
      readable: get("readable") === "true",
      editable: get("editable") === "true",
      line: indexOfWithLine(xml, m.index),
    });
  }
  return blocks;
}

function parseObjectPermissions(xml) {
  const blocks = [];
  const re = /<objectPermissions>([\s\S]*?)<\/objectPermissions>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    const body = m[1];
    const get = (tag) => {
      const t = new RegExp(`<${tag}>([^<]*)<\\/${tag}>`).exec(body);
      return t ? t[1].trim() : null;
    };
    const bool = (tag) => get(tag) === "true";
    blocks.push({
      object: get("object"),
      allowCreate: bool("allowCreate"),
      allowRead: bool("allowRead"),
      allowEdit: bool("allowEdit"),
      allowDelete: bool("allowDelete"),
      viewAllFields: bool("viewAllFields"),
      editAllFields: bool("editAllFields"),
      viewAllRecords: bool("viewAllRecords"),
      modifyAllRecords: bool("modifyAllRecords"),
      line: indexOfWithLine(xml, m.index),
    });
  }
  return blocks;
}

function parseUserPermissions(xml) {
  const blocks = [];
  const re = /<userPermissions>([\s\S]*?)<\/userPermissions>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    const body = m[1];
    const get = (tag) => {
      const t = new RegExp(`<${tag}>([^<]*)<\\/${tag}>`).exec(body);
      return t ? t[1].trim() : null;
    };
    blocks.push({
      name: get("name"),
      enabled: get("enabled") === "true",
      line: indexOfWithLine(xml, m.index),
    });
  }
  return blocks;
}

const findings = [];   // {file, severity, type, message, ...}
const objectsReferenced = new Set();

for (const file of permSetFiles) {
  let xml;
  try { xml = readFileSync(file, "utf8"); }
  catch (e) { findings.push({ file, severity: "error", type: "read-error", message: e.message }); continue; }

  // (1) Forbid <fieldPermissions> entirely.
  const fps = parseFieldPermissions(xml);
  for (const fp of fps) {
    findings.push({
      file, severity: "block", type: "field-permissions-forbidden",
      field: fp.field || "(unspecified)",
      line: fp.line,
      message: `<fieldPermissions> block at line ${fp.line} (${fp.field || "unspecified field"}) — framework policy is object-level access only. Delete this block. If the persona must not see this field, route them through a different permission set, or use sharing/encryption. Per-field FLS in PermissionSet XML is the #1 cause of deploy failures.`,
    });
  }

  // (2) Object permissions must use viewAllFields/editAllFields.
  const ops = parseObjectPermissions(xml);
  let opCount = 0;
  let hasRead = new Set();
  let hasDelete = new Set();
  for (const op of ops) {
    if (!op.object) continue;
    opCount++;
    objectsReferenced.add(op.object);
    if (op.allowRead) hasRead.add(op.object);
    if (op.allowDelete) hasDelete.add(op.object);

    if (!op.viewAllFields) {
      findings.push({
        file, severity: "block", type: "missing-view-all-fields",
        object: op.object, line: op.line,
        message: `<objectPermissions> for ${op.object} (line ${op.line}) is missing <viewAllFields>true. Framework policy: object-level access uses viewAllFields=true so all eligible fields are visible without per-field FLS.`,
      });
    }
    if (op.allowEdit && !op.editAllFields) {
      findings.push({
        file, severity: "block", type: "missing-edit-all-fields",
        object: op.object, line: op.line,
        message: `<objectPermissions> for ${op.object} (line ${op.line}) sets allowEdit=true but is missing <editAllFields>true. Edit access at the object level requires editAllFields=true.`,
      });
    }
    if (op.modifyAllRecords || op.viewAllRecords) {
      findings.push({
        file, severity: "warn", type: "wide-record-access",
        object: op.object, line: op.line,
        message: `<objectPermissions> for ${op.object} grants viewAllRecords/modifyAllRecords. Confirm this is intentional — these bypass sharing.`,
      });
    }
  }
  // Read+Delete combined on the same object — split.
  for (const obj of hasRead) {
    if (hasDelete.has(obj)) {
      findings.push({
        file, severity: "block", type: "read-and-delete-combined",
        object: obj,
        message: `${obj} grants both Read and Delete in the same permission set. Split into two sets.`,
      });
    }
  }
  if (opCount > 10) {
    findings.push({
      file, severity: "block", type: "too-many-objects",
      message: `${opCount} <objectPermissions> blocks in one set; framework policy caps at 10. Split into multiple sets.`,
    });
  }

  // (3) Reject ViewAllData / ModifyAllData in functional sets.
  const ups = parseUserPermissions(xml);
  for (const up of ups) {
    if (!up.enabled) continue;
    if (up.name === "ViewAllData" || up.name === "ModifyAllData") {
      findings.push({
        file, severity: "block", type: "view-or-modify-all-data",
        line: up.line,
        message: `<userPermissions> grants ${up.name} (line ${up.line}). Framework policy forbids this in functional permission sets — use object-level permissions instead.`,
      });
    }
  }
}

// --- (online) verify objects exist in target org -------------------------

mkdirSync(opts.cacheDir, { recursive: true });
const cacheKey = (org) => join(opts.cacheDir, `org-objects.${org || "offline"}.json`);

function objectExistsInOrg(object) {
  // Light Tooling API check — EntityDefinition has one row per addressable
  // SObject in the org (standard + custom). Fast and authoritative.
  const q = `SELECT QualifiedApiName FROM EntityDefinition WHERE QualifiedApiName='${object}'`;
  let raw;
  try {
    raw = execFileSync(
      "sf",
      ["data", "query", "--use-tooling-api", "--target-org", opts.targetOrg,
        "--query", q, "--json"],
      { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }
    );
  } catch (e) {
    findings.push({
      file: "(org)", severity: "block", type: "tooling-query-failed",
      object, message: `Tooling API query failed for ${object}: ${e.stderr?.toString() || e.message}`,
    });
    return null;
  }
  let parsed;
  try { parsed = JSON.parse(raw); }
  catch (e) {
    findings.push({
      file: "(org)", severity: "block", type: "tooling-parse-failed",
      object, message: `Could not parse Tooling API response for ${object}: ${e.message}`,
    });
    return null;
  }
  return (parsed.result?.records || []).length > 0;
}

if (!opts.offline) {
  const cacheFile = cacheKey(opts.targetOrg);
  let orgObjects = {};
  if (existsSync(cacheFile)) {
    try { orgObjects = JSON.parse(readFileSync(cacheFile, "utf8")); }
    catch { orgObjects = {}; }
  }
  for (const object of objectsReferenced) {
    if (object in orgObjects) continue;
    const exists = objectExistsInOrg(object);
    if (exists === null) continue;
    orgObjects[object] = exists;
    if (!exists) {
      findings.push({
        file: "(org)", severity: "block", type: "object-not-in-org",
        object,
        message: `${object} is referenced in <objectPermissions> but not found in target org. Either it doesn't exist, the user lacks access, or there's a namespace mismatch.`,
      });
    }
  }
  try { writeFileSync(cacheFile, JSON.stringify(orgObjects, null, 2)); } catch {}
} else if (!opts.json) {
  console.error("(--offline mode: skipping org existence check; reporting only XML-derived findings)");
}

// --- emit results --------------------------------------------------------

if (opts.json) {
  process.stdout.write(JSON.stringify({
    workspace: opts.workspace,
    targetOrg: opts.targetOrg,
    permSetCount: permSetFiles.length,
    objectsReferenced: [...objectsReferenced],
    findings,
  }, null, 2));
  process.stdout.write("\n");
} else {
  if (findings.length === 0) {
    console.log(`✓ ${permSetFiles.length} permission set(s) clean — object-level access policy satisfied, no <fieldPermissions> blocks.`);
  } else {
    const groups = new Map();
    for (const f of findings) {
      if (!groups.has(f.file)) groups.set(f.file, []);
      groups.get(f.file).push(f);
    }
    console.log(`✗ ${findings.length} finding(s) across ${groups.size} permission set file(s):\n`);
    for (const [file, fs] of groups) {
      console.log(`### ${file}`);
      for (const f of fs) {
        const tag = `[${f.severity.toUpperCase()}]`;
        const ctx = f.field ? ` (${f.field})` : f.object ? ` (${f.object})` : "";
        console.log(`  ${tag} ${f.type}${ctx}: ${f.message}`);
      }
      console.log();
    }
  }
}

const blocking = findings.filter(f => f.severity === "block" || f.severity === "error").length;
process.exit(blocking > 0 ? 1 : 0);
