#!/usr/bin/env node
// REQ-B: Permission-set FLS pre-flight.
//
// For every `.permissionset-meta.xml` under the workspace, validate that every
// <fieldPermissions> entry is FLS-eligible against the target org. Salesforce
// rejects FLS on required / formula / master-detail / auto-number fields, plus
// any field that doesn't exist in the org. Catching these locally is ~1-3
// seconds; catching them via `sf project deploy validate` is ~60-90 seconds
// per round trip.
//
// Usage:
//   node tools/sf-preflight/check-permsets.mjs \
//     --workspace force-app \
//     --target-org <alias> \
//     [--cache-dir .adlc/.cache] \
//     [--offline]                 # parse only — skip the Tooling API call
//     [--json]                    # emit machine-readable findings
//
// Exit codes:
//   0 — no findings
//   1 — at least one finding (BLOCK)
//   2 — invocation error (bad args, missing org, etc.)

import { readFileSync, readdirSync, statSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, basename, dirname } from "node:path";

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

// --- parse <fieldPermissions> blocks -------------------------------------
// Tag-based parsing — avoids pulling a heavy XML dependency. Salesforce metadata
// is line-oriented and consistent.

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
      field: get("field"),                     // "Account.SSN__c"
      readable: get("readable") === "true",
      editable: get("editable") === "true",
    });
  }
  return blocks;
}

const findings = [];   // {file, severity, type, message, field?, object?}
const fieldsByObject = new Map();   // object → Set<field>

for (const file of permSetFiles) {
  let xml;
  try { xml = readFileSync(file, "utf8"); }
  catch (e) { findings.push({ file, severity: "error", type: "read-error", message: e.message }); continue; }
  const fps = parseFieldPermissions(xml);
  for (const fp of fps) {
    if (!fp.field || !fp.field.includes(".")) {
      findings.push({
        file, severity: "block", type: "malformed-field-ref",
        message: `<fieldPermissions> with missing or unqualified <field> entry: ${JSON.stringify(fp)}`,
      });
      continue;
    }
    const [object, field] = fp.field.split(".", 2);
    if (!fieldsByObject.has(object)) fieldsByObject.set(object, new Set());
    fieldsByObject.get(object).add(field);
    // stash for the rule pass below
    fp.__file = file;
    fp.__object = object;
    fp.__field = field;
  }
}

// --- query the org (or load from cache) ----------------------------------

mkdirSync(opts.cacheDir, { recursive: true });
const cacheKey = (org) => join(opts.cacheDir, `org-fields.${org || "offline"}.json`);

function describeFromOrg(object) {
  // Pull eligibility-relevant attributes from FieldDefinition for one object.
  const q = `SELECT QualifiedApiName, IsCalculated, IsAutoNumber, IsCompound, ` +
            `DataType, ValueTypeId, IsNillable, IsCreatable, IsUpdatable ` +
            `FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName='${object}'`;
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
  return parsed.result?.records || [];
}

let orgFields = {};
if (opts.offline) {
  if (!opts.json) console.error("(--offline mode: skipping Tooling API; reporting only XML-derived findings)");
} else {
  const cacheFile = cacheKey(opts.targetOrg);
  if (existsSync(cacheFile)) {
    try { orgFields = JSON.parse(readFileSync(cacheFile, "utf8")); }
    catch { orgFields = {}; }
  }
  for (const object of fieldsByObject.keys()) {
    if (orgFields[object]) continue;
    const records = describeFromOrg(object);
    if (records === null) continue;
    const map = {};
    for (const r of records) {
      map[r.QualifiedApiName] = {
        isCalculated: !!r.IsCalculated,
        isAutoNumber: !!r.IsAutoNumber,
        isCompound: !!r.IsCompound,
        dataType: r.DataType || "",
        valueTypeId: r.ValueTypeId || "",
        isNillable: r.IsNillable !== false,
        isCreatable: !!r.IsCreatable,
        isUpdatable: !!r.IsUpdatable,
      };
    }
    orgFields[object] = map;
  }
  try { writeFileSync(cacheFile, JSON.stringify(orgFields, null, 2)); } catch {}
}

// --- apply the FLS-eligibility rules -------------------------------------

for (const file of permSetFiles) {
  const xml = readFileSync(file, "utf8");
  const fps = parseFieldPermissions(xml);
  for (const fp of fps) {
    if (!fp.field || !fp.field.includes(".")) continue;   // already flagged
    const [object, field] = fp.field.split(".", 2);
    const desc = orgFields[object]?.[field];
    if (!desc && !opts.offline) {
      findings.push({
        file, severity: "block", type: "field-not-in-org",
        field: fp.field,
        message: `${fp.field} not found in target org. Either it doesn't exist, the user lacks access to FieldDefinition for it, or there's a namespace mismatch.`,
      });
      continue;
    }
    if (!desc) continue;
    // Master-detail: never eligible for FLS.
    if (desc.dataType === "MasterDetail") {
      findings.push({
        file, severity: "block", type: "master-detail",
        field: fp.field,
        message: `${fp.field} is a master-detail relationship. FLS cannot be set on master-detail fields; remove the <fieldPermissions> entry.`,
      });
      continue;
    }
    // Auto-number: editable must be false.
    if (desc.isAutoNumber && fp.editable) {
      findings.push({
        file, severity: "block", type: "auto-number-editable",
        field: fp.field,
        message: `${fp.field} is auto-number; editable must be false.`,
      });
    }
    // Formula (calculated): editable must be false.
    if (desc.isCalculated && fp.editable) {
      findings.push({
        file, severity: "block", type: "formula-editable",
        field: fp.field,
        message: `${fp.field} is a formula field; editable must be false (read-only by definition).`,
      });
    }
    // Required field — Salesforce treats Nillable=false + IsCreatable=true as
    // "required on insert"; FLS on truly required fields fails deploy.
    if (desc.isNillable === false && desc.isCreatable && desc.isUpdatable) {
      findings.push({
        file, severity: "block", type: "required-field",
        field: fp.field,
        message: `${fp.field} is required (IsNillable=false). Required fields cannot have FLS — remove the <fieldPermissions> entry. The platform always grants access to required fields.`,
      });
    }
  }
}

// --- emit results --------------------------------------------------------

if (opts.json) {
  process.stdout.write(JSON.stringify({
    workspace: opts.workspace,
    targetOrg: opts.targetOrg,
    permSetCount: permSetFiles.length,
    objectsCheckedAgainstOrg: opts.offline ? [] : Object.keys(orgFields),
    findings,
  }, null, 2));
  process.stdout.write("\n");
} else {
  if (findings.length === 0) {
    console.log(`✓ ${permSetFiles.length} permission set(s) clean — no FLS issues detected.`);
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
        const fld = f.field ? ` (${f.field})` : f.object ? ` (${f.object})` : "";
        console.log(`  ${tag} ${f.type}${fld}: ${f.message}`);
      }
      console.log();
    }
  }
}

process.exit(findings.length > 0 ? 1 : 0);
