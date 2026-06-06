---
name: canary
description: Salesforce sandbox → staging → prod promotion gate. Runs `sf project deploy validate` against each environment in turn, runs `sf agent test run` (when Agentforce is in scope) as a smoke gate, and only proceeds to the next environment on a clean validate + smoke pass. **Prod is validate-only — `/canary` never runs `sf project deploy start` against the prod alias under any circumstances; it surfaces the validation id and tells the user to deploy manually.** Use when the user says "canary deploy", "promote to staging", "promote to prod", "smoke test the deploy", or wants validation confidence before going live.
argument-hint: Optional environment to promote TO (sandbox | staging | prod) — auto-promotes from previous if omitted
---

# /canary — Salesforce sandbox → staging → prod promotion gate

You are promoting a Salesforce change set through the project's environment ladder: **sandbox → staging → prod**. Each step runs `sf project deploy validate` (a no-op deploy that surfaces every error without writing changes), then `sf agent test run` against the Agentforce test specs when Agentforce is in scope. For sandbox and staging, a clean validate is followed by the actual `sf project deploy start`. **For prod, `/canary` always halts at validate.** It captures the validation id from the validate response and instructs the user to run `sf project deploy quick --job-id <id>` manually — the skill itself never runs the deploy command against the prod alias.

This is the SFDC analog to a Cloud Run canary. Salesforce has no traffic-shifted revisions; the promotion model is **validate → deploy → smoke → verify** through a sequence of orgs.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Current directory: !`pwd`
- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Configured orgs: !`grep -A 5 "^orgs:" .adlc/config.yml 2>/dev/null || echo "No .adlc/config.yml — orgs not configured"`
- Default sf org: !`sf org display --json 2>/dev/null | head -20 || echo "sf org not configured"`
- Salesforce rules: !`cat .adlc/context/salesforce-rules.md 2>/dev/null || cat ~/.claude/skills/.adlc/context/salesforce-rules.md 2>/dev/null || echo "No salesforce-rules found"`
- SF quality checklist: !`cat .adlc/partials/sf-quality-checklist.md 2>/dev/null || cat ~/.claude/skills/partials/sf-quality-checklist.md 2>/dev/null || echo "No sf-quality-checklist found"`

## Input

Target environment: $ARGUMENTS (one of `sandbox`, `staging`, `prod`; auto-promotes from the previous environment if omitted)

## Prerequisites

1. `sf` CLI v2 installed and authenticated against the target org
2. `.adlc/config.yml` declares an `orgs:` block with `sandbox`, `staging`, `prod` aliases
3. The branch under test is merged-or-ready and the working tree is clean
4. `sf project deploy preview` runs cleanly against the local manifest before invoking `/canary`

If `.adlc/config.yml` is absent OR has no `orgs:` block, stop and tell the user to add it (see `presets/sfdc-core.yml` for the shape).

## Org resolution

Read `.adlc/config.yml`. The `orgs:` block maps environment label → sf CLI org alias:

```yaml
orgs:
  sandbox: "<sandbox-alias>"
  staging: "<staging-alias>"
  prod:    "<prod-alias>"

agentforce_test_specs: "force-app/main/default/agentTests"   # optional
playwright_specs: "tests/e2e"                                 # optional — directory of Playwright UI specs
```

Resolve the target alias for `$ARGUMENTS`. If absent in the config, halt with a clear message naming the missing key.

## Promotion order

Default flow when `$ARGUMENTS` is omitted: **sandbox → staging → prod**, with each step gated on the previous step's clean result. The skill records the last-promoted environment in `.adlc/specs/REQ-xxx-*/pipeline-state.json` `canary` block (when invoked from `/proceed`) so a resumed run picks up at the next step.

Explicit `$ARGUMENTS` skips ahead — useful when sandbox deploy is owned by CI and the user just wants `/canary staging` or `/canary prod`.

## Instructions

### Step 1: Pre-flight — confirm target org

```sh
ALIAS=$(grep -A 5 '^orgs:' .adlc/config.yml | awk -v env="$ENV:" '$1 == env {print $2}' | tr -d '"')
sf org display --target-org "$ALIAS" --json | jq -r '.result.username, .result.instanceUrl'
```

Surface the username + instance URL to the user before any deploy/validate. If the alias does not resolve, halt.

### Step 2a: Local pre-flight (REQ-B + REQ-F)

Before paying for a server-side `sf project deploy validate`, run two local pre-flight passes. Each takes seconds; together they catch the entire class of FLS / cross-reference / missing-field-in-org errors that otherwise burn 60-90s per validate round-trip.

**Pass 1 — perm-set FLS (REQ-B)** — queries the org's `FieldDefinition` (Tooling API) and validates every `<fieldPermissions>` entry against the FLS-eligibility rules (required, formula, master-detail, auto-number, missing-from-org).

```sh
sh tools/sf-preflight/check.sh permsets \
  --workspace force-app \
  --target-org "$ALIAS"
```

Skip this pass only when the diff has no perm-set / perm-set-group XML.

**Pass 2 — generalized metadata cross-reference (REQ-F)** — workspace-internal check. Catches perm-sets referencing missing Apex classes / apps / tabs / record types, layouts referencing missing custom fields, and FlexiPages referencing unknown sObjects.

```sh
sh tools/sf-preflight/check.sh metadata --workspace force-app
```

This pass requires no org access, so always run it.

**Pass 3 — org-config presence (the "never pipeline these" gate)** — verifies that every Connected App, Named Credential, External Credential, Auth Provider, Certificate, Remote Site Setting, and License referenced by the spec exists in the target org *before* the deploy runs. These artifacts are intentionally excluded from the pipeline (`/spec` Step 1.7) — they live in Setup. This gate converts the spec's pre-deploy assumption into a verified precondition so a deploy that depends on a missing Named Credential fails here in seconds rather than mid-deploy with a confusing FieldIntegrity error.

```sh
SPEC=$(ls .adlc/specs/REQ-${REQ_NUM}-*/requirement.md 2>/dev/null | head -1)
[ -n "$SPEC" ] || { echo "no REQ spec found — skipping org-config gate" && SKIP_PASS3=1; }
```

For each artifact type below, extract referenced names from the spec's `## External Dependencies` and `## Assumptions` sections (case-insensitive match on the artifact-type keyword, then capture the quoted name token). Query the target org for presence. Any miss is a **BLOCK** finding.

| Artifact | Metadata type | Query approach |
|---|---|---|
| Connected App | `ConnectedApp` | `sf data query --use-tooling-api --target-org "$ALIAS" --query "SELECT Name FROM ConnectedApplication WHERE Name IN (<names>)"` |
| Named Credential | `NamedCredential` | `sf org list metadata --target-org "$ALIAS" --metadata-type NamedCredential --json` then filter |
| External Credential | `ExternalCredential` | `sf org list metadata --target-org "$ALIAS" --metadata-type ExternalCredential --json` |
| Auth Provider | `AuthProvider` | `sf org list metadata --target-org "$ALIAS" --metadata-type AuthProvider --json` |
| Certificate | `Certificate` | `sf org list metadata --target-org "$ALIAS" --metadata-type Certificate --json` |
| Remote Site Setting | `RemoteSiteSetting` | `sf org list metadata --target-org "$ALIAS" --metadata-type RemoteSiteSetting --json` |

For each missing artifact, emit a BLOCK finding of the form:
```
BLOCK: Connected App 'Acme_Stripe_Integration' is referenced by REQ-xxx as a pre-deploy assumption but does not exist in <alias>. Create it in Setup → App Manager before re-running /canary. The pipeline never creates this artifact programmatically — secrets, OAuth callbacks, and consumer keys must be wired through the UI.
```

If the spec's External Dependencies + Assumptions reference no org-config artifacts, this pass is a no-op (zero queries, zero output). Do not emit a "skipped" line.

If any of the three pre-flight passes exits non-zero (BLOCK findings), **STOP** — surface the findings verbatim and refuse to call `sf project deploy validate`. Each finding is actionable. The user fixes the metadata (or creates the missing org-config artifact in Setup) and re-runs `/canary`. WARN-level findings (e.g., unknown-object heuristic, missing-custom-field on a layout) surface in the report but do not block — they're often false positives on cross-package deploys.

### Step 2b: Resolve `--test-level` from the diff (REQ-D)

`--test-level RunLocalTests` runs every Apex test in the org. For metadata-only changes (perm-sets, layouts, LWC bundles, Flows without Apex callouts) that's pure waste — often 5-10 minutes per validate against a mature org. Pick the cheapest level that still surfaces real regressions, with the floor lifting per environment.

```sh
BASE="${BASE_REF:-origin/main}"
APEX_TOUCHED=$(git diff --name-only "$BASE...HEAD" 2>/dev/null \
  | grep -E '\.(cls|trigger)$' || true)
APEX_NONTEST=$(echo "$APEX_TOUCHED" | grep -vE '(Test|_Test)\.cls$' || true)
HAS_APEX=$( [ -n "$APEX_NONTEST" ] && echo 1 || echo 0 )
```

Decision matrix:

| Environment | Apex in diff? | `--test-level` | Tests run via `--tests` |
|---|---|---|---|
| `sandbox` | no | `NoTestRun` | (none) |
| `sandbox` | yes | `RunSpecifiedTests` | derived list (below) |
| `staging` | no | `RunSpecifiedTests` | smoke tests from `.adlc/config.yml` `salesforce.smoke_tests` (if set), else `RunLocalTests` |
| `staging` | yes | `RunLocalTests` | n/a |
| `prod` | any | `RunLocalTests` | n/a (production-equivalent) |

**Deriving the test list** when `RunSpecifiedTests` is selected with Apex in the diff:

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
TESTS="$TESTS $(echo "$APEX_TOUCHED" | grep -E '(Test|_Test)\.cls$' \
  | sed 's|.*/||;s|\.cls$||' | tr '\n' ' ')"
TESTS=$(echo "$TESTS" | tr -s ' ' '\n' | sort -u | tr '\n' ' ')
```

If `TESTS` is empty after derivation despite `HAS_APEX=1` (e.g., a brand-new class with no test yet), **fall back to `RunLocalTests`** rather than running zero tests — a class with no test class will be caught by REQ-A's coverage gate but the deploy still needs *something* to run against it.

Persist the resolved level into `.adlc/.cache/canary-test-level-<env>.txt` so Step 3 reuses it.

### Step 2: Validate (mandatory — never skipped)

Run `sf project deploy validate` against the target org with the test level resolved in Step 2b:

```sh
TEST_LEVEL=$(cat ".adlc/.cache/canary-test-level-${ENV}.txt")
TEST_FLAGS="--test-level $TEST_LEVEL"
[ "$TEST_LEVEL" = "RunSpecifiedTests" ] && TEST_FLAGS="$TEST_FLAGS --tests $TESTS"

sf project deploy validate \
  --target-org "$ALIAS" \
  $TEST_FLAGS \
  --wait 60 \
  --json
```

Capture the result. **Always extract the validation id** (`.result.id` in the JSON response) and surface it in the report — for prod runs this id IS the artifact the user needs for the manual deploy step. On any failure (compilation error, test failure, governor-limit failure, missing dependency), STOP — do not proceed. Surface the full error report from `--json` output.

`RunLocalTests` is the Salesforce-default for production-equivalent validation; the diff-aware policy above is what makes the sandbox round-trip cheap. The project's CI config in `.github/workflows/*` may override the staging or prod entries — honor it when present.

### Step 3: Deploy (sandbox / staging only — prod ALWAYS halts at validate)

**Branching by target environment:**

#### Step 3a — sandbox / staging: run the deploy

If validate passes AND target is `sandbox` or `staging`, run the actual deploy. Reuse the resolved test level from Step 2b — running a different (heavier) set at deploy time would invalidate Step 2's promise:

```sh
TEST_LEVEL=$(cat ".adlc/.cache/canary-test-level-${ENV}.txt")
TEST_FLAGS="--test-level $TEST_LEVEL"
[ "$TEST_LEVEL" = "RunSpecifiedTests" ] && TEST_FLAGS="$TEST_FLAGS --tests $TESTS"

sf project deploy start \
  --target-org "$ALIAS" \
  $TEST_FLAGS \
  --wait 120 \
  --json
```

The `Bash(sf project deploy start:*)` permission is on the `ask` list in `.claude/settings.json` — Claude Code surfaces an ask-prompt before running. The user confirms once per environment.

After deploy completes, capture the deploy id and the full result list. Surface succeeded/failed component counts.

#### Step 3b — prod: validate-only, hand off to the user

**When `$ENV == prod`, `/canary` MUST stop after a clean validate.** Do NOT run `sf project deploy start --target-org "$ALIAS"` under any circumstances. Do NOT run `sf project deploy quick --target-org "$ALIAS"` either. The skill's job for prod ends at "validate clean, here is the id."

This is a **hard rule, not a default that can be overridden via flag, prompt, or `--auto-approve`-style argument.** Any future change that wires an automatic prod deploy must edit this contract first. Reasons:
- Prod deploys carry change-management and audit-trail obligations the agent cannot satisfy (CAB approval, release-notes attestation, on-call coverage confirmation).
- The validation id is reusable for ~10 days, so manual deploy is not a time-pressure event — the user can schedule it.
- A manual deploy is the only step where a human is provably in the loop, which is the point of the prod gate.

After Step 2 returns a clean validation, do all of the following and then halt:

1. Extract the validation id from the validate JSON: `VALIDATION_ID=$(... | jq -r '.result.id')`
2. Confirm the validation is reusable: query `sf project deploy report --target-org "$ALIAS" --job-id "$VALIDATION_ID" --json` and assert `result.checkOnly == true` and `result.status == "Succeeded"`.
3. Surface a deploy hand-off block in the final report (see Output template below). The block MUST contain:
   - The full validation id, copy-pasteable.
   - The exact `sf project deploy quick --target-org "$ALIAS" --job-id "$VALIDATION_ID" --wait 60` command for the user to run.
   - A reminder that `sf project deploy quick` reuses the validation result and skips re-running tests, but only works while the validation is still cached server-side (typically ~10 days).
   - A reminder to run any post-deploy gate (Agentforce smoke, Playwright `@prod-safe` smoke) AFTER the manual deploy completes — those steps in this skill have already been skipped because there is no fresh deploy yet.
4. Set the report's "Next step" line to: `Manual prod deploy required. Run the command above and re-invoke /canary post-deploy verification if you need it.`
5. Stop. Do NOT proceed to Step 4 (Agentforce smoke), Step 4b (Playwright smoke), Step 5 (Verify), or Step 7 (Auto-promote) for the prod target. The Step 6 state-record write still happens — record `result: validate-only` for the prod entry.

If the user explicitly types `/canary prod --deploy` or any similar flag asking for a real deploy, refuse: "Prod deploy is intentionally manual. The validation id is <id>; run `sf project deploy quick --target-org <alias> --job-id <id>` yourself." Do NOT pattern-match around this.

### Step 4: Agentforce smoke gate (only when in scope; SKIPPED on prod)

**If `$ENV == prod`, Step 3b has already halted the pipeline — Step 4 does not run.** There is no fresh deploy to smoke-test against until the user runs the manual `sf project deploy quick` command, so running `sf agent test run` here would either smoke-test the previous prod state (misleading "pass") or fail because the new agents aren't active yet (misleading "fail"). The hand-off block in Step 3b reminds the user to run this gate after their manual deploy.

When `.adlc/config.yml` `salesforce.industries:` includes `agentforce` AND `agentforce_test_specs:` points at a real directory, run `sf agent test run` as the smoke gate:

```sh
sf agent test run \
  --target-org "$ALIAS" \
  --api-name "<agent-api-name>" \
  --output-dir "reports/agent-tests/$ENV" \
  --result-format json \
  --wait 30
```

For each spec under `<agentforce_test_specs>/`, invoke the spec, capture pass/fail, and roll up. On any spec failure, STOP — recommend the user investigate before promoting to the next environment. Do NOT auto-rollback (Salesforce has no revision-based rollback; the corrective action is a forward-fix deploy).

If Agentforce is NOT in scope, skip this step silently. Do not emit a "skipped" line — that's noise.

### Step 4b: Playwright UI smoke gate (only when in scope; SKIPPED on prod)

**If `$ENV == prod`, Step 3b has already halted the pipeline — Step 4b does not run.** Same reasoning as Step 4: there is no new metadata in prod yet, so a Playwright smoke would assert against the old surface. The hand-off block in Step 3b includes the exact `npx playwright test --project=prod` command the user should run after their manual deploy lands, restricted to `@prod-safe` specs.

When `.adlc/config.yml` declares `playwright_specs:` AND that directory contains at least one `*.spec.ts`/`*.spec.js`, run Playwright as a real-browser smoke against the just-deployed org. This catches regressions that a server-side Apex test cannot — broken FlexiPage layouts, LWC bundles that fail to load, OmniScript steps that no longer render, login-flow drift.

```sh
# Resolve org credentials → storageState (one-time per run)
ORG_URL=$(sf org display --target-org "$ALIAS" --json | jq -r '.result.instanceUrl')
ORG_USER=$(sf org display --target-org "$ALIAS" --json | jq -r '.result.username')
sf org open --target-org "$ALIAS" --url-only --json > "reports/playwright/$ENV/login-url.json"

# Run the suite against this environment
PLAYWRIGHT_BASE_URL="$ORG_URL" \
PLAYWRIGHT_LOGIN_URL_FILE="reports/playwright/$ENV/login-url.json" \
npx playwright test \
  --config "$(grep '^playwright_specs:' .adlc/config.yml | awk '{print $2}' | tr -d '"' | xargs dirname)/../playwright.config.ts" \
  --project="$ENV" \
  --reporter=json \
  --output "reports/playwright/$ENV"
```

Roll up pass/fail. On any spec failure, **STOP** — surface the failing spec name, the screenshot/trace path written under `reports/playwright/$ENV/`, and recommend a forward-fix. Do NOT auto-promote to the next environment.

If `playwright_specs:` is absent OR the directory is empty, skip this step silently. Production projects that rely solely on Apex/Jest coverage are still supported.

`prod` policy: never run Playwright specs that mutate org state against the prod alias. Specs marked `@prod-safe` (read-only smoke: load page, assert selector, log out) MAY run; everything else is filtered out via `--grep "@prod-safe"` when `$ENV == prod`. Specs that don't carry the tag are skipped with a one-line note in the report.

### Step 5: Verify (three-tier coverage policy — REQ-A)

After deploy + smoke gate, run a final verification:

```sh
# Confirm the deployed code matches what we built locally — list the latest deploy
sf project deploy report --target-org "$ALIAS" --json | jq '.result.status'

# Capture full coverage data from the org
sf apex run test --target-org "$ALIAS" --test-level RunLocalTests --wait 10 \
  --code-coverage --result-format json > .adlc/.cache/coverage-$ALIAS.json
```

**Read the coverage policy from `.adlc/config.yml`** (defaults shown):

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

**Apply the policy:**

1. **Org-level (always)** — extract org coverage from the test run summary:
   ```sh
   ORG_COV=$(jq '.result.summary.testRunCoverage' .adlc/.cache/coverage-$ALIAS.json | tr -d '%')
   ```
   - `ORG_COV < ORG_FLOOR` → **BLOCK** promotion. Critical: org coverage breaches the platform/policy minimum.
   - `ORG_FLOOR ≤ ORG_COV < ORG_TARGET` → **WARN** but allow. Major: org below project target. Surface in the report; do not auto-promote past staging until a follow-up REQ pushes it above target.
   - `ORG_COV ≥ ORG_TARGET` → **PASS** the org-level gate.

2. **Per-class (brownfield mode only)** — for each Apex class in the diff:
   ```sh
   if [ "$MODE" = "brownfield" ]; then
     CHANGED=$(git diff --name-only "origin/$BASE...HEAD" | grep -E '\.cls$' | grep -vE '(Test|_Test)\.cls$' \
       | sed 's|.*/||;s|\.cls$||' | sort -u)
     [ -z "$CHANGED" ] && echo "no Apex classes changed — skipping per-class gate" && return
     QUOTED=$(echo "$CHANGED" | awk '{printf "%s'\''%s'\''", sep, $0; sep=","}')
     sf data query --use-tooling-api --target-org "$ALIAS" --json \
       --query "SELECT ApexClassOrTrigger.Name, NumLinesCovered, NumLinesUncovered \
                FROM ApexCodeCoverageAggregate \
                WHERE ApexClassOrTrigger.Name IN ($QUOTED)"
   fi
   ```
   For each row, compute `pct = NumLinesCovered * 100 / (NumLinesCovered + NumLinesUncovered)`.
   - `pct < CLASS_FLOOR` → **BLOCK** promotion. Critical: class coverage breaches policy.
   - `pct ≥ CLASS_FLOOR` → pass.

3. **Greenfield mode** — skip step 2 entirely; emit per-class numbers as informational only.

4. **`diff_only: true`** — replace the per-class query with a per-line `ApexCodeCoverage` query restricted to the changed line ranges. Implementation note: this requires parsing `git diff -U0` for hunk line numbers and intersecting with the `Coverage` field's `coveredLines`/`uncoveredLines` arrays. Defer to a follow-up REQ if the project has not opted in.

**Surface the result** in the canary report — see the Coverage block in `## Output`.

### Step 6: Record state

If `pipeline-state.json` exists for the current REQ (we're inside `/proceed`):
1. Add a `canary` entry to `phaseHistory` with the result (passed/failed) per environment
2. Include: target org alias, deploy id, validate duration, test pass/fail count, agent test result, coverage %
3. The entry's `startedAt` and `completedAt` MUST be the literal output of `date -u +"%Y-%m-%dT%H:%M:%SZ"` run via the Bash tool — once at canary entry start, once at completion. Do NOT type a timestamp in. The LLM has no reliable clock; freelanced values pollute dashboard Duration/Active telemetry.

Otherwise, just emit the report to stdout.

### Step 7: Auto-promote OR halt

- **Auto-promote** to the next environment in the ladder (sandbox → staging) ONLY when `$ARGUMENTS` was omitted AND every gate passed. The auto-promote ladder ends at staging — it never includes prod.
- **Always halt** before attempting prod, even on auto-promote: emit a single line "Validate-only run for prod required. Re-invoke `/canary prod` when ready." and stop. The prod step must be a deliberate, separate invocation.
- **For `/canary prod` specifically**: after Step 3b emits the manual-deploy hand-off block, Step 7 is a no-op halt. There is no further environment to auto-promote to, and the actual deploy is owned by the user.

## Output

```
## Canary Promotion Report

REQ: REQ-xxx
Target: <env>
Org: <username> (<instance URL>)

### Validate
- Test level: RunLocalTests
- Tests run: NNN
- Tests passed: NNN
- Tests failed: 0
- Components validated: NNN
- Validation id: <validation-id>   # always emitted; required hand-off artifact for prod
- Result: ✓ clean (or full error report on failure)

### Deploy (sandbox / staging only)
- Deploy id: <id>
- Components succeeded: NNN
- Components failed: 0
- Wall time: NNs

### Manual deploy hand-off (prod only — replaces the Deploy block)
- Target: <prod-alias>
- Validation id: <validation-id>
- Status: Validated (checkOnly=true, status=Succeeded)
- Reuse window: ~10 days from validation timestamp
- **Run this manually when ready:**
  ```sh
  sf project deploy quick --target-org <prod-alias> --job-id <validation-id> --wait 60
  ```
- Post-deploy gates skipped by /canary (re-run them yourself once the deploy lands):
  - `sf agent test run` (if Agentforce in scope)
  - `npx playwright test --project=prod` (if `playwright_specs:` in scope; only `@prod-safe`-tagged specs)

### Agentforce smoke (if in scope)
- Specs run: NNN
- Pass: NNN
- Fail: 0
- Result: ✓ clean

### Playwright UI smoke (if in scope)
- Specs run: NNN
- Pass: NNN
- Fail: 0
- Skipped (not @prod-safe): NNN  (only on prod runs)
- Trace artifacts: reports/playwright/<env>/
- Result: ✓ clean

### Verification — coverage (three-tier policy)
- Mode: <greenfield | brownfield>
- Org coverage: NN.N%  (org_target NN, org_floor NN — ✓ pass | ⚠ warn | ✗ block)
- Per-changed-class (brownfield only):
  - <ClassName1>: NN.N%  (class_floor NN — ✓/✗)
  - <ClassName2>: NN.N%  (class_floor NN — ✓/✗)
- Final org status: <status>

Next step: <auto-promoted to staging | run `/canary prod` | halted because of <reason>>
```

## Failure modes

- **Validate fails**: stop. Surface the deployment errors verbatim. Do NOT attempt the deploy.
- **Deploy fails after validate succeeded** (sandbox/staging): rare (validate is server-side). Surface the failure; the corrective action is a forward-fix deploy, not a rollback.
- **Prod validate succeeds but the validation id cannot be extracted from the JSON**: stop. Surface the raw validate response so the user can pull the id manually. Do NOT guess or fall back to `sf project deploy report --use-most-recent` — the wrong id silently deploys the wrong artifact.
- **Validation id is older than the reuse window** at the time the user runs the manual deploy: `sf project deploy quick` will reject with "no validated deployment found for id". Re-run `/canary prod` to produce a fresh validation; do not bypass with a non-quick deploy.
- **Agentforce smoke fails**: stop before promoting further. Recommend investigation; do NOT auto-fix.
- **Playwright smoke fails**: stop before promoting further. Surface the failing spec, the path to the trace/video under `reports/playwright/$ENV/`, and the assertion message. Do NOT auto-fix; UI failures usually need the trace viewer (`npx playwright show-trace`) to diagnose.
- **Coverage drops below 75%**: surface as a Major finding; do NOT block promotion automatically (production policy may differ — let the user decide).

## What This Skill Does NOT Do

- Does NOT roll back. Salesforce has no revision-based rollback; the corrective action is a forward-fix deploy.
- Does NOT manage scratch orgs (use `sf org create scratch` directly).
- Does NOT modify metadata. It only validates, deploys (sandbox/staging), runs tests, and reports.
- Does NOT bypass `.claude/settings.json` ask-prompts. `sf project deploy start` and `sf agent activate` always prompt.
- Does NOT auto-promote to prod. Prod is always a deliberate, separate `/canary prod` invocation.
- **Does NOT run any deploy command against the prod alias** — not `sf project deploy start`, not `sf project deploy quick`, not `sf project deploy resume`. The skill validates against prod and hands the validation id to the user; the user runs the deploy themselves. This is non-negotiable and not configurable via flag.
- Does NOT run Agentforce or Playwright smoke gates against prod, because there is no fresh deploy yet at the time `/canary` exits. Re-run those gates after the manual deploy lands.
