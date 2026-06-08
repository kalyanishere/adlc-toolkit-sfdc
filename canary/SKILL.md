---
name: canary
description: Salesforce sandbox deploy gate. Runs `sf project deploy validate` then `sf project deploy start` against the configured sandbox org, with `sf agent test run` and Playwright UI smoke as post-deploy gates when in scope. **Sandbox-only by design** — staging and production deploys are intentionally out of scope for this skill (the project's CI/CD pipeline owns those promotions). Use when the user says "canary deploy", "deploy to sandbox", "smoke test the deploy", or wants validation + deploy confidence after a merge.
argument-hint: (no arguments — always targets the sandbox alias from `.adlc/config.yml`)
---

# /canary — Salesforce sandbox deploy gate

You are deploying a merged Salesforce change set to the project's sandbox org so the team can smoke-test it before any further promotion.

`/canary` runs the canonical sequence: `sf project deploy validate` → `sf project deploy start` → `sf agent test run` (when Agentforce is in scope) → `npx playwright test` (when UI is in scope) → coverage verification. Each gate halts on first failure with a forward-fix recommendation. **Staging and production deploys are out of scope** — they belong to the project's CI/CD pipeline (GitHub Actions, Gearset, Copado, etc.). The ADLC pipeline ships changes to sandbox; humans + CI promote from there.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Current directory: !`pwd`
- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Configured sandbox alias: !`grep -A 3 "^orgs:" .adlc/config.yml 2>/dev/null | grep "sandbox:" || echo "No .adlc/config.yml — orgs not configured"`
- Default sf org: !`sf org display --json 2>/dev/null | head -20 || echo "sf org not configured"`
- Salesforce rules: !`cat .adlc/context/salesforce-rules.md 2>/dev/null || cat ~/.claude/skills/.adlc/context/salesforce-rules.md 2>/dev/null || echo "No salesforce-rules found"`
- SF quality checklist: !`cat .adlc/partials/sf-quality-checklist.md 2>/dev/null || cat ~/.claude/skills/partials/sf-quality-checklist.md 2>/dev/null || echo "No sf-quality-checklist found"`

## Input

`/canary` takes no arguments. The target is always the sandbox alias from `.adlc/config.yml` (`orgs.sandbox`). If the user types `/canary staging`, `/canary prod`, or any other env name, refuse and point them at their CI/CD pipeline.

## Prerequisites

1. `sf` CLI v2 installed and authenticated against the sandbox alias.
2. `.adlc/config.yml` declares `orgs.sandbox: "<alias>"`. `/init` populates this automatically from `basename($PWD)`; the user can authenticate with `sf org login web --alias <alias>` to make the value usable.
3. The branch under test is merged-or-ready and the working tree is clean.
4. `sf project deploy preview` runs cleanly against the local manifest before invoking `/canary`.

If `.adlc/config.yml` is absent OR `orgs.sandbox` is missing/empty, stop and tell the user to add it (see `presets/sfdc-core.yml` for the shape).

## Org resolution

```sh
ALIAS=$(awk '/^orgs:/{f=1; next} f && /^[[:space:]]+sandbox:/{sub(/^[[:space:]]+sandbox:[[:space:]]*/,""); gsub(/["'\'']/,""); sub(/[[:space:]]*#.*$/,""); print; exit}' .adlc/config.yml)
[ -n "$ALIAS" ] || { echo "ERROR: orgs.sandbox is missing or empty in .adlc/config.yml"; exit 1; }
sf org display --target-org "$ALIAS" --json | jq -r '.result.username, .result.instanceUrl'
```

Surface the username + instance URL to the user before any deploy/validate. If the alias does not resolve to an authenticated org, halt.

## Instructions

### Step 1: Local pre-flight (no org needed for passes 2 + 3)

Before paying for a server-side `sf project deploy validate`, run three local pre-flight passes. Each takes seconds; together they catch the entire class of FLS / cross-reference / missing-field-in-org errors that otherwise burn 60-90s per validate round-trip.

**Pass 1 — perm-set FLS** — queries the org's `FieldDefinition` (Tooling API) and validates every `<fieldPermissions>` entry against the FLS-eligibility rules (system fields, required, formula, master-detail, auto-number, compound, missing-from-org).

```sh
sh tools/sf-preflight/check.sh permsets --workspace force-app --target-org "$ALIAS"
```

Skip this pass only when the diff has no perm-set / perm-set-group XML.

**Pass 2 — generalized metadata cross-reference** — workspace-internal check. Catches perm-sets referencing missing Apex classes / apps / tabs / record types, layouts referencing missing custom fields, and FlexiPages referencing unknown sObjects.

```sh
sh tools/sf-preflight/check.sh metadata --workspace force-app
```

Always runs (no org access required).

**Pass 3 — org-config presence (the "never pipeline these" gate)** — verifies that every Connected App, Named Credential, External Credential, Auth Provider, Certificate, Remote Site Setting, and License referenced by the spec exists in the target org *before* the deploy runs. These artifacts are intentionally excluded from the pipeline (`/spec` Step 1.7) — they live in Setup. This gate converts the spec's pre-deploy assumption into a verified precondition so a deploy that depends on a missing Named Credential fails here in seconds rather than mid-deploy.

For each artifact type referenced by the spec's `## External Dependencies` and `## Assumptions` sections, query the sandbox for presence. Any miss is a **BLOCK** finding with a one-line remediation pointing the user at Setup.

If any of the three pre-flight passes exits non-zero (BLOCK findings), **STOP** — surface the findings verbatim and refuse to call `sf project deploy validate`. WARN-level findings surface in the report but do not block.

### Step 2: Resolve `--test-level` from the diff

`--test-level RunLocalTests` runs every Apex test in the org. For metadata-only changes (perm-sets, layouts, LWC bundles, Flows without Apex callouts) that's pure waste — often 5-10 minutes per validate against a mature org. Pick the cheapest level that still surfaces real regressions.

```sh
BASE="${BASE_REF:-origin/main}"
APEX_TOUCHED=$(git diff --name-only "$BASE...HEAD" 2>/dev/null | grep -E '\.(cls|trigger)$' || true)
APEX_NONTEST=$(echo "$APEX_TOUCHED" | grep -vE '(Test|_Test)\.cls$' || true)
HAS_APEX=$( [ -n "$APEX_NONTEST" ] && echo 1 || echo 0 )
```

Decision matrix (sandbox is the only environment now):

| Apex in diff? | `--test-level` | Tests run via `--tests` |
|---|---|---|
| no | `NoTestRun` | (none) |
| yes | `RunSpecifiedTests` | derived list (below) |

**Deriving the test list** when `RunSpecifiedTests` is selected:

```sh
# For each touched non-test class, list candidate test classes by the standard
# *Test / _Test / Test_ naming conventions. Always include any explicitly
# changed *Test.cls so a fix to the test itself runs.
TESTS=""
for f in $APEX_NONTEST; do
  base=$(basename "$f" .cls)
  for cand in "${base}Test" "${base}_Test" "Test_${base}"; do
    if find force-app -type f -name "${cand}.cls" 2>/dev/null | grep -q .; then
      TESTS="$TESTS $cand"
    fi
  done
done
TESTS="$TESTS $(echo "$APEX_TOUCHED" | grep -E '(Test|_Test)\.cls$' | sed 's|.*/||;s|\.cls$||' | tr '\n' ' ')"
TESTS=$(echo "$TESTS" | tr -s ' ' '\n' | sort -u | tr '\n' ' ')
```

If `TESTS` is empty after derivation despite `HAS_APEX=1` (e.g., a brand-new class with no test yet), **fall back to `RunLocalTests`** — a class with no test class will be caught by the coverage gate, but the deploy still needs *something* to run.

Persist the resolved level into `.adlc/.cache/canary-test-level.txt` so Step 4 reuses it.

### Step 3: Validate (mandatory — never skipped)

```sh
TEST_LEVEL=$(cat .adlc/.cache/canary-test-level.txt)
TEST_FLAGS="--test-level $TEST_LEVEL"
[ "$TEST_LEVEL" = "RunSpecifiedTests" ] && TEST_FLAGS="$TEST_FLAGS --tests $TESTS"

sf project deploy validate \
  --target-org "$ALIAS" \
  $TEST_FLAGS \
  --wait 60 \
  --json
```

Capture the result. Extract the validation id (`.result.id`) and surface it in the report. On any failure (compilation error, test failure, governor-limit failure, missing dependency), STOP — do not proceed. Surface the full error report from the `--json` output.

### Step 4: Deploy

If validate passes, run the actual deploy. Reuse the resolved test level — running a different (heavier) set at deploy time would invalidate Step 3's promise:

```sh
sf project deploy start \
  --target-org "$ALIAS" \
  $TEST_FLAGS \
  --wait 120 \
  --json
```

The `Bash(sf project deploy start:*)` permission is in the project's `.claude/settings.json`. Capture the deploy id and the full result list. Surface succeeded/failed component counts. On any failure, STOP with the deployment errors verbatim.

### Step 5: Agentforce smoke gate (only when in scope)

When `.adlc/config.yml` `salesforce.industries:` includes `agentforce` AND `agentforce_test_specs:` points at a real directory, run `sf agent test run`:

```sh
sf agent test run \
  --target-org "$ALIAS" \
  --api-name "<agent-api-name>" \
  --output-dir "reports/agent-tests/sandbox" \
  --result-format json \
  --wait 30
```

For each spec under `<agentforce_test_specs>/`, invoke the spec, capture pass/fail, roll up. On any spec failure, STOP — recommend the user investigate. Do NOT auto-rollback (Salesforce has no revision-based rollback; corrective action is a forward-fix deploy).

If Agentforce is NOT in scope, skip this step silently.

### Step 6: Playwright UI smoke gate (only when in scope)

When `.adlc/config.yml` declares `playwright_specs:` AND that directory contains at least one `*.spec.ts`/`*.spec.js`, run Playwright as a real-browser smoke against the sandbox. This catches regressions Apex tests can't — broken FlexiPage layouts, LWC bundles that fail to load, OmniScript steps that no longer render, login-flow drift.

```sh
ORG_URL=$(sf org display --target-org "$ALIAS" --json | jq -r '.result.instanceUrl')
sf org open --target-org "$ALIAS" --url-only --json > "reports/playwright/sandbox/login-url.json"

PLAYWRIGHT_BASE_URL="$ORG_URL" \
PLAYWRIGHT_LOGIN_URL_FILE="reports/playwright/sandbox/login-url.json" \
npx playwright test \
  --project=sandbox \
  --reporter=json \
  --output "reports/playwright/sandbox"
```

Roll up pass/fail. On any spec failure, **STOP** — surface the failing spec name, the screenshot/trace path under `reports/playwright/sandbox/`, and recommend a forward-fix.

If `playwright_specs:` is absent OR the directory is empty, skip this step silently.

### Step 7: Verify (three-tier coverage policy)

After deploy + smoke gates, run a final verification:

```sh
sf project deploy report --target-org "$ALIAS" --json | jq '.result.status'

sf apex run test --target-org "$ALIAS" --test-level RunLocalTests --wait 10 \
  --code-coverage --result-format json > .adlc/.cache/coverage-$ALIAS.json
```

**Read the coverage policy from `.adlc/config.yml`:**

```sh
MODE=$(awk '/^[[:space:]]*coverage:/{f=1} f && /^[[:space:]]*mode:/{print $2; exit}' .adlc/config.yml | tr -d '"')
ORG_FLOOR=$(awk '/^[[:space:]]*coverage:/{f=1} f && /^[[:space:]]*org_floor:/{print $2; exit}' .adlc/config.yml)
ORG_TARGET=$(awk '/^[[:space:]]*coverage:/{f=1} f && /^[[:space:]]*org_target:/{print $2; exit}' .adlc/config.yml)
CLASS_FLOOR=$(awk '/^[[:space:]]*coverage:/{f=1} f && /^[[:space:]]*class_floor:/{print $2; exit}' .adlc/config.yml)
MODE=${MODE:-brownfield}
ORG_FLOOR=${ORG_FLOOR:-75}
ORG_TARGET=${ORG_TARGET:-80}
CLASS_FLOOR=${CLASS_FLOOR:-75}
```

**Apply:**

1. **Org-level (always):** `ORG_COV < ORG_FLOOR` blocks; `ORG_FLOOR ≤ ORG_COV < ORG_TARGET` warns; `ORG_COV ≥ ORG_TARGET` passes.
2. **Per-class (brownfield mode only)** — for each Apex class in the diff, query `ApexCodeCoverageAggregate` and assert `pct ≥ CLASS_FLOOR`. Below floor blocks.
3. **Greenfield mode** — skip step 2; emit per-class numbers as informational only.

### Step 8: Record state

If `pipeline-state.json` exists for the current REQ (we're inside `/proceed`):
1. Add a `canary` entry to `phaseHistory` with the result (passed/failed) and per-step timings.
2. Include: target org alias, deploy id, validate duration, test pass/fail count, agent test result, Playwright result, coverage %.
3. The entry's `startedAt` and `completedAt` MUST be the literal output of `date -u +"%Y-%m-%dT%H:%M:%SZ"` run via Bash — once at canary entry start, once at completion. Do NOT type a timestamp.

Otherwise, just emit the report to stdout.

## Output

```
## Canary Sandbox Deploy Report

REQ: REQ-xxx
Target: sandbox (<alias>)
Org: <username> (<instance URL>)

### Validate
- Test level: <NoTestRun | RunSpecifiedTests | RunLocalTests>
- Tests run: NNN
- Tests passed: NNN
- Tests failed: 0
- Components validated: NNN
- Validation id: <validation-id>
- Result: ✓ clean (or full error report on failure)

### Deploy
- Deploy id: <id>
- Components succeeded: NNN
- Components failed: 0
- Wall time: NNs

### Agentforce smoke (if in scope)
- Specs run: NNN
- Pass: NNN
- Fail: 0
- Result: ✓ clean

### Playwright UI smoke (if in scope)
- Specs run: NNN
- Pass: NNN
- Fail: 0
- Trace artifacts: reports/playwright/sandbox/
- Result: ✓ clean

### Verification — coverage (three-tier policy)
- Mode: <greenfield | brownfield>
- Org coverage: NN.N%  (org_target NN, org_floor NN — ✓ pass | ⚠ warn | ✗ block)
- Per-changed-class (brownfield only):
  - <ClassName1>: NN.N%  (class_floor NN — ✓/✗)
- Final org status: <status>

Next step: <Sandbox deploy clean — promote via your CI/CD pipeline | halted because of <reason>>
```

## Failure modes

- **Validate fails:** stop. Surface the deployment errors verbatim. Do NOT attempt the deploy.
- **Deploy fails after validate succeeded:** rare (validate is server-side). Surface the failure; the corrective action is a forward-fix deploy, not a rollback.
- **Agentforce smoke fails:** stop. Recommend investigation; do NOT auto-fix.
- **Playwright smoke fails:** stop. Surface the failing spec, the path to the trace/video under `reports/playwright/sandbox/`, and the assertion message. Do NOT auto-fix; UI failures usually need the trace viewer (`npx playwright show-trace`) to diagnose.
- **Coverage drops below floor:** Critical block (see Step 7).

## What This Skill Does NOT Do

- **Does NOT deploy to staging or production.** Sandbox is the only target. Staging and prod promotions are owned by the project's CI/CD pipeline (GitHub Actions, Gearset, Copado, etc.). If the user types `/canary staging` or `/canary prod`, refuse and point them at the CI workflow file or release manager.
- Does NOT roll back. Salesforce has no revision-based rollback; the corrective action is a forward-fix deploy.
- Does NOT manage scratch orgs (use `sf org create scratch` directly).
- Does NOT modify metadata. It validates, deploys, runs tests, reports.
- Does NOT bypass `.claude/settings.json` ask-prompts. `sf project deploy start` and `sf agent activate` always prompt.
