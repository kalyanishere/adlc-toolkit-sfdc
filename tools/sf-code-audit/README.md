# sf-code-audit (vendored)

Vendored copy of [salesforce-code-audit-tool v1.2.13](https://github.com/) — the static analyzer for Apex governor-limit violations, FLS/CRUD security gaps, LWC XSS issues, test-class anti-patterns, etc.

This directory ships **two CLIs**:

| CLI | Mode | Needs an org? | Used by |
|---|---|---|---|
| `audit_source.py` | **source-only** — walks `force-app/`, runs the Apex + LWC analyzers against local files | No | ADLC `/reflect` Phase 5a gate, CI |
| `salesforce_audit.py` | **org-connected** — pulls metadata via `sfdx`, full report with coverage, perms, etc. | Yes | Manual deep audits (post-deploy, periodic) |

The pipeline gate uses **`audit_source.py`** because it (a) needs no org, (b) runs in the worktree, (c) is fast, and (d) emits machine-readable JSON for the gate plus a Markdown summary for the developer.

---

## What gets checked (source-only mode)

The Apex analyzer (`pattern_matcher.py`) catches ~40 violation classes:

- **Governor limits** — SOQL/DML in loops (direct + indirect via call-chain), non-restrictive queries, missing WHERE/LIMIT, wildcard filters, redundant SOQL, expensive methods in loops, busy-loop delays.
- **Security** — missing CRUD/FLS, SOQL injection, missing `with sharing`, hardcoded credentials, hardcoded record IDs, `System.debug` of sensitive data.
- **Async/Triggers** — `@future` misuse, async in trigger context, recursive trigger risk, EventBus without callback, mixed DML.
- **Tests** — missing assertions, `@isTest(SeeAllData=true)`, missing persona-based testing.

The LWC analyzer (`lwc_analyzer.py`) catches:

- XSS via `escape={false}`
- Missing error handling on Apex/promise calls
- Missing double-click prevention on submit handlers
- Unsafe HTML rendering (`innerHTML`, contextual)
- Insecure API calls
- `console.log` of sensitive data
- Hardcoded credentials in JS
- Improper data binding

Severity: `CRITICAL | HIGH | MEDIUM | LOW`. The pipeline gate fails on `CRITICAL` and `HIGH` by default — configurable per project in `.adlc/config.yml` under `audit.fail_on`.

---

## Source-only CLI

```bash
python3 audit_source.py [--root .] [--files-from PATH] [--fail-on CRITICAL,HIGH] \
                       [--json-out PATH] [--md-out PATH] [--skip-paths a,b,c] \
                       [--quiet]
```

**Flags:**

- `--root` — project root containing `sfdx-project.json` and `force-app/` (default: cwd).
- `--files-from PATH` — restrict the scan to the listed files (one per line). Use `git diff --name-only` to populate. Diff-mode is what the pipeline uses by default.
- `--fail-on CRITICAL,HIGH` — comma-separated severities that cause exit code 1 when count > 0. Use `NONE` to disable gating (advise-only).
- `--json-out` / `--md-out` — write machine-readable + human-readable reports.
- `--skip-paths` — additional repo-relative paths to skip (defaults already cover `node_modules`, `.git`, `.sfdx`, `.adlc`, etc.).
- `--quiet` — suppress stdout summary; reports still written.

**Exit codes:**

- `0` — gate passed (or `--fail-on NONE`).
- `1` — gate failed.
- `2` — usage / I/O error.

**JSON shape:**

```jsonc
{
  "tool": "sf-code-audit-source",
  "version": "1.2.13",
  "started_at": "2026-06-13T13:09:00+00:00",
  "root": "/abs/path",
  "scope": "diff scope (.adlc/runtime/audit/diff-files.txt)",
  "files_scanned": { "apex": 12, "triggers": 1, "lwc_bundles": 5 },
  "summary": { "CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 0, "INFO": 0, "TOTAL": 3 },
  "findings": [
    {
      "kind": "apex",
      "file": "force-app/main/default/classes/AccountSvc.cls",
      "line": 42,
      "severity": "HIGH",
      "rule": "Missing CRUD/FLS Check",
      "snippet": "Account a = [SELECT ...]",
      "recommendation": "Use WITH USER_MODE or Security.stripInaccessible.",
      "is_direct": true,
      "call_chain": null
    }
  ]
}
```

---

## Where this fires in the ADLC pipeline

`partials/run-source-audit.sh` is the single entrypoint the toolkit calls. It:

1. Reads `audit:` block from `.adlc/config.yml` (fail-on severities, scope, report dir).
2. Resolves the audit tool from `.adlc/tools/sf-code-audit/` (consumer-local copy after `/init`) or `$TOOLKIT_HOME/tools/sf-code-audit/` (toolkit fallback).
3. When `scope: diff`, derives the changed-files list from `git diff` against the merge-base with `main`.
4. Calls `audit_source.py` with the right flags.
5. Returns the exit code unchanged so the calling skill (`/reflect`, `/proceed`) can gate on it.

By default the gate fires inside `/reflect` (Phase 5a — before the multi-agent review fan-out) so toolkit-generated code is checked **before** `/canary` deploys to sandbox. The Markdown summary lands at `.adlc/runtime/audit/source-audit.md` for the developer to review.

---

## Disabling / loosening the gate

Edit `.adlc/config.yml`:

```yaml
audit:
  enabled: false          # turns the gate off entirely (not recommended)
  fail_on: "CRITICAL"     # only block on CRITICAL; HIGH becomes advisory
  fail_on: "NONE"         # advise-only; never blocks the pipeline
  scope: full             # scan everything in force-app/, not just the diff
  skip_paths:             # paths to skip in addition to defaults
    - "force-app/main/default/staticresources"
```

---

## Org-connected mode (manual)

The full v1.2.13 CLI is still available for periodic deep audits:

```bash
python3 salesforce_audit.py --sfdx my-sandbox-alias --output-dir ./audit-reports
# or use the wrapper:
./run_audit.sh my-sandbox-alias ./audit-reports
```

This produces an Excel workbook + Markdown summary covering coverage stats, permission-set hygiene, metadata health, and the same code-pattern findings as source-only mode plus org-only checks.

**Dependencies for org-connected mode are auto-installed by `/init`.**

`/init` Step 7.8 provisions a project-local virtual env at `.adlc/tools/sf-code-audit/.venv` and pip-installs `requirements.txt` into it (simple-salesforce, pandas, openpyxl, reportlab, etc.). Devs never type `pip` — the venv is rebuilt on the next `/init` if it gets removed, and the venv directory is gitignored so each clone provisions its own.

The wrapper (`partials/run-source-audit.sh`) prefers `.venv/bin/python` when present and falls back to system `python3` otherwise. Source-only mode is stdlib-only, so the gate keeps working even if the venv install fails (offline, firewalled, missing `python3-venv` package, etc.) — only the org-connected CLI needs the deps.

To force a manual rebuild:

```bash
rm -rf .adlc/tools/sf-code-audit/.venv
# Then re-run /init, or:
python3 -m venv .adlc/tools/sf-code-audit/.venv
.adlc/tools/sf-code-audit/.venv/bin/python -m pip install -r .adlc/tools/sf-code-audit/requirements.txt
```

Skip auto-install on `/init` (offline / firewalled bootstrap):

```bash
ADLC_INIT_SKIP_AUDIT_PIP=1 /init
```

---

## Updating the vendored copy

The auto-update is **disabled** in this vendored copy (`update_config.json` has `enabled: false`). To pull a new upstream version:

1. Drop the new release zip into `tools/sf-code-audit/` (overwrite `pattern_matcher.py`, `lwc_analyzer.py`, `grading_engine.py`, `salesforce_audit.py`, `report_generator.py`, `sf_utils.py`, `tool_version.json`).
2. Re-run the smoke test (`/tmp/audit-smoke` synthetic project) and confirm the new analyzer's severity output still maps to the `audit_source.py` schema.
3. Commit the bump.

The toolkit's `/init` copies `tools/sf-code-audit/` into every consumer's `.adlc/tools/sf-code-audit/` on bootstrap; existing consumers can re-run `/init` to pick up the new version, or use `/template-drift` to surface what changed.

---

## Attribution

This directory vendors the `salesforce-code-audit-tool` v1.2.13 by its original author, copied from the upstream release. See `UPSTREAM-README.md` for the original documentation and `GRADING_SYSTEM_DETAILED.md` / `VIOLATION_CATEGORIES_CORRECTED.md` for the detection rule details.
