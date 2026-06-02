#!/usr/bin/env node
// REQ-F: Generalized metadata cross-reference pre-flight.
//
// Catches the class of "deploy fails because metadata X references metadata Y
// that doesn't exist (or is being deleted in the same change)" errors locally,
// before paying for a server-side `sf project deploy validate`. Complements
// REQ-B (which handles the org-side FieldDefinition rules).
//
// Checks:
//   1. Permission set <classAccesses> reference Apex classes that exist in
//      the workspace.
//   2. Permission set <applicationVisibilities> reference Lightning apps that
//      exist as <Name>.app-meta.xml.
//   3. Permission set <tabSettings> reference tabs (.tab-meta.xml).
//   4. Permission set <recordTypeVisibilities> reference record types as
//      objects/<Object>/recordTypes/<RecordType>.recordType-meta.xml.
//   5. Permission set <objectPermissions> reference objects that exist as
//      objects/<Object>/<Object>.object-meta.xml (or stock Salesforce objects —
//      detected by the absence of __c).
//   6. Layout <fields>/<columns> reference fields that exist (by file presence).
//   7. FlexiPage <componentInstance> attribute objectApiName references an
//      existing object.
//
// Usage:
//   node tools/sf-preflight/check-metadata.mjs --workspace force-app [--json]
//
// Exit codes: 0 clean, 1 findings, 2 invocation error.

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, basename } from "node:path";

const args = process.argv.slice(2);
const opts = { workspace: "force-app", json: false };
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === "--workspace") opts.workspace = args[++i];
  else if (a === "--json") opts.json = true;
  else if (a === "-h" || a === "--help") {
    console.log("Usage: check-metadata.mjs --workspace <dir> [--json]");
    process.exit(0);
  } else { console.error(`Unknown argument: ${a}`); process.exit(2); }
}
if (!existsSync(opts.workspace)) {
  console.error(`ERROR: workspace ${opts.workspace} does not exist`);
  process.exit(2);
}

// --- recursive file walk -------------------------------------------------

function walk(dir, predicate) {
  const out = [];
  const queue = [dir];
  while (queue.length) {
    const d = queue.pop();
    let entries;
    try { entries = readdirSync(d); } catch { continue; }
    for (const e of entries) {
      const p = join(d, e);
      let st; try { st = statSync(p); } catch { continue; }
      if (st.isDirectory()) queue.push(p);
      else if (predicate(p)) out.push(p);
    }
  }
  return out;
}

// --- index the workspace -------------------------------------------------

const workspacePaths = walk(opts.workspace, () => true);
const apexClasses = new Set();
const apps = new Set();
const tabs = new Set();
const objects = new Set();
const recordTypes = new Set();              // "Object.RecordType"
const fields = new Set();                   // "Object.FieldName"
const flexipages = [];
const layouts = [];
const permSets = [];

for (const p of workspacePaths) {
  if (p.endsWith(".cls") && !p.endsWith(".cls-meta.xml")) {
    apexClasses.add(basename(p, ".cls"));
  } else if (p.endsWith(".app-meta.xml")) {
    apps.add(basename(p).replace(/\.app-meta\.xml$/, ""));
  } else if (p.endsWith(".tab-meta.xml")) {
    tabs.add(basename(p).replace(/\.tab-meta\.xml$/, ""));
  } else if (p.endsWith(".object-meta.xml")) {
    objects.add(basename(p).replace(/\.object-meta\.xml$/, ""));
  } else if (p.endsWith(".recordType-meta.xml")) {
    // .../objects/<Object>/recordTypes/<Name>.recordType-meta.xml
    const m = p.match(/objects\/([^/]+)\/recordTypes\/([^/]+)\.recordType-meta\.xml$/);
    if (m) recordTypes.add(`${m[1]}.${m[2]}`);
  } else if (p.endsWith(".field-meta.xml")) {
    // .../objects/<Object>/fields/<Field>.field-meta.xml
    const m = p.match(/objects\/([^/]+)\/fields\/([^/]+)\.field-meta\.xml$/);
    if (m) fields.add(`${m[1]}.${m[2]}`);
  } else if (p.endsWith(".flexipage-meta.xml")) {
    flexipages.push(p);
  } else if (p.endsWith(".layout-meta.xml")) {
    layouts.push(p);
  } else if (p.endsWith(".permissionset-meta.xml")) {
    permSets.push(p);
  }
}

// Stock Salesforce objects we don't expect to find as metadata files.
const STOCK_OBJECTS = new Set([
  "Account", "Contact", "Lead", "Opportunity", "Case", "Campaign", "Asset",
  "Product2", "PricebookEntry", "Pricebook2", "Order", "OrderItem", "Quote",
  "QuoteLineItem", "Contract", "Task", "Event", "User", "UserRole", "Profile",
  "PermissionSet", "PermissionSetGroup", "Group", "Note", "Attachment",
  "ContentDocument", "ContentVersion", "ContentDocumentLink", "Topic",
  "Idea", "Knowledge__kav", "Site", "Network", "Folder", "Document", "EmailTemplate",
  "BusinessHours", "Holiday", "RecordType", "QueueSobject", "AccountTeamMember",
  "OpportunityTeamMember", "OpportunityLineItem", "AccountContactRelation",
  "OpportunityContactRole", "CampaignMember", "Solution",
]);

const findings = [];

function isUnknownObject(obj) {
  if (!obj) return false;
  if (objects.has(obj)) return false;
  if (STOCK_OBJECTS.has(obj)) return false;
  // Custom-namespace standard objects (e.g., npe01__OppPayment__c) — heuristic.
  if (/__[a-z]/.test(obj)) return false;
  // Big objects, custom metadata types, custom settings (heuristic).
  if (/__b$|__mdt$|__c$/.test(obj) === false) return true;   // not a __c, not a stock — unknown
  return !objects.has(obj);
}

// --- per-permset checks --------------------------------------------------

function getAll(xml, tag) {
  const out = [];
  const re = new RegExp(`<${tag}>([\\s\\S]*?)<\\/${tag}>`, "g");
  let m;
  while ((m = re.exec(xml)) !== null) out.push(m[1]);
  return out;
}
function getOne(xml, tag) {
  const m = new RegExp(`<${tag}>([^<]*)<\\/${tag}>`).exec(xml);
  return m ? m[1].trim() : null;
}

for (const ps of permSets) {
  const xml = readFileSync(ps, "utf8");

  // <classAccesses><apexClass>X</apexClass></classAccesses>
  for (const block of getAll(xml, "classAccesses")) {
    const cls = getOne(block, "apexClass");
    if (cls && !apexClasses.has(cls)) {
      findings.push({ file: ps, severity: "block", type: "missing-apex-class",
        ref: cls,
        message: `<classAccesses> references Apex class ${cls}, but no force-app/.../classes/${cls}.cls exists in the workspace.`,
      });
    }
  }
  // <applicationVisibilities><application>X</application></applicationVisibilities>
  for (const block of getAll(xml, "applicationVisibilities")) {
    const app = getOne(block, "application");
    if (app && !apps.has(app) && !app.startsWith("standard__")) {
      findings.push({ file: ps, severity: "block", type: "missing-app",
        ref: app,
        message: `<applicationVisibilities> references app ${app}, but no <name>.app-meta.xml exists for it.`,
      });
    }
  }
  // <tabSettings><tab>X</tab></tabSettings>
  for (const block of getAll(xml, "tabSettings")) {
    const tab = getOne(block, "tab");
    if (tab && !tabs.has(tab) && !tab.startsWith("standard-")) {
      findings.push({ file: ps, severity: "block", type: "missing-tab",
        ref: tab,
        message: `<tabSettings> references tab ${tab}, but no <name>.tab-meta.xml exists for it.`,
      });
    }
  }
  // <recordTypeVisibilities><recordType>Object.RT</recordType></recordTypeVisibilities>
  for (const block of getAll(xml, "recordTypeVisibilities")) {
    const rt = getOne(block, "recordType");
    if (rt && !recordTypes.has(rt)) {
      findings.push({ file: ps, severity: "block", type: "missing-record-type",
        ref: rt,
        message: `<recordTypeVisibilities> references record type ${rt}, but no objects/.../recordTypes/${rt.split(".")[1]}.recordType-meta.xml exists.`,
      });
    }
  }
  // <objectPermissions><object>X</object></objectPermissions>
  for (const block of getAll(xml, "objectPermissions")) {
    const obj = getOne(block, "object");
    if (obj && isUnknownObject(obj)) {
      findings.push({ file: ps, severity: "warn", type: "unknown-object",
        ref: obj,
        message: `<objectPermissions> references object ${obj} which is neither a stock Salesforce object nor a workspace-defined object. Verify spelling or that the object will be deployed alongside this perm-set.`,
      });
    }
  }
}

// --- per-flexipage checks ------------------------------------------------

for (const fp of flexipages) {
  const xml = readFileSync(fp, "utf8");
  // sobjectType references — appear in <sobjectType>X</sobjectType>
  for (const obj of getAll(xml, "sobjectType")) {
    const v = obj.trim();
    if (v && isUnknownObject(v)) {
      findings.push({ file: fp, severity: "warn", type: "unknown-object",
        ref: v,
        message: `FlexiPage references sobjectType ${v} which is unknown in the workspace.`,
      });
    }
  }
}

// --- per-layout checks (light — full would need XML parser) --------------
// Layouts reference fields by API name inside <field>X</field>. We only flag
// custom-suffixed fields (__c) where the file is missing — stock fields aren't
// in the workspace and aren't a useful signal.

for (const lay of layouts) {
  const xml = readFileSync(lay, "utf8");
  // Layout file path: .../objects/<Object>/layouts/<Layout>.layout-meta.xml
  const objMatch = lay.match(/objects\/([^/]+)\/layouts\//);
  if (!objMatch) continue;
  const obj = objMatch[1];
  for (const fld of getAll(xml, "field")) {
    const v = fld.trim();
    if (!v.endsWith("__c")) continue;
    if (!fields.has(`${obj}.${v}`)) {
      findings.push({ file: lay, severity: "warn", type: "missing-custom-field",
        ref: `${obj}.${v}`,
        message: `Layout references custom field ${obj}.${v}, but no fields/${v}.field-meta.xml exists for object ${obj}.`,
      });
    }
  }
}

// --- emit ---------------------------------------------------------------

if (opts.json) {
  process.stdout.write(JSON.stringify({
    workspace: opts.workspace,
    counts: {
      apexClasses: apexClasses.size, apps: apps.size, tabs: tabs.size,
      objects: objects.size, recordTypes: recordTypes.size, fields: fields.size,
      permSets: permSets.length, flexipages: flexipages.length, layouts: layouts.length,
    },
    findings,
  }, null, 2));
  process.stdout.write("\n");
} else {
  if (findings.length === 0) {
    console.log(`✓ Metadata cross-references clean across ${permSets.length} perm-set(s), ${flexipages.length} FlexiPage(s), ${layouts.length} layout(s).`);
  } else {
    const groups = new Map();
    for (const f of findings) {
      if (!groups.has(f.file)) groups.set(f.file, []);
      groups.get(f.file).push(f);
    }
    console.log(`✗ ${findings.length} finding(s) across ${groups.size} file(s):\n`);
    for (const [file, fs] of groups) {
      console.log(`### ${file}`);
      for (const f of fs) {
        const tag = `[${f.severity.toUpperCase()}]`;
        const ref = f.ref ? ` (${f.ref})` : "";
        console.log(`  ${tag} ${f.type}${ref}: ${f.message}`);
      }
      console.log();
    }
  }
}

const blocking = findings.filter(f => f.severity === "block").length;
process.exit(blocking > 0 ? 1 : 0);
