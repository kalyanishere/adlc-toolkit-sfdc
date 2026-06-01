---
name: canary
description: Salesforce sandbox → staging → prod promotion gate. Runs `sf project deploy validate` against each environment in turn, runs `sf agent test run` (when Agentforce is in scope) as a smoke gate, and only proceeds to the next environment on a clean validate + smoke pass. Production deploy is gated by an ask-prompt in .claude/settings.json. Use when the user says "canary deploy", "promote to staging", "promote to prod", "smoke test the deploy", or wants validation confidence before going live.
argument-hint: Optional environment to promote TO (sandbox | staging | prod) — auto-promotes from previous if omitted
---

# /canary — Salesforce sandbox → staging → prod promotion gate

You are promoting a Salesforce change set through the project's environment ladder: **sandbox → staging → prod**. Each step runs `sf project deploy validate` (a no-op deploy that surfaces every error without writing changes), then `sf agent test run` against the Agentforce test specs when Agentforce is in scope. Only on a clean pass does the actual deploy run, and prod is always gated by an ask-prompt — never auto-approved.

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

### Step 2: Validate (mandatory — never skipped)

Run `sf project deploy validate` against the target org. This is a server-side no-op deploy that catches every error without writing changes:

```sh
sf project deploy validate \
  --target-org "$ALIAS" \
  --test-level RunLocalTests \
  --wait 60 \
  --json
```

Capture the result. On any failure (compilation error, test failure, governor-limit failure, missing dependency), STOP — do not proceed to the actual deploy. Surface the full error report from `--json` output.

`--test-level RunLocalTests` runs every test in the package directories, which is the Salesforce-default for production-equivalent validation. For sandboxes the user may pass `--test-level RunSpecifiedTests` if the project's CI does that already; honor whatever the project's CI config in `.github/workflows/*` declares.

### Step 3: Deploy (sandbox/staging only — prod is ask-gated separately)

If validate passes AND target is `sandbox` or `staging`, run the actual deploy:

```sh
sf project deploy start \
  --target-org "$ALIAS" \
  --test-level RunLocalTests \
  --wait 120 \
  --json
```

The `Bash(sf project deploy start:*)` permission is on the `ask` list in `.claude/settings.json` — Claude Code surfaces an ask-prompt before running. The user confirms once per environment.

For **prod**, the actual deploy command is the same but the user MUST explicitly approve via the ask-prompt; do not phrase the prompt as a question that has a default-yes interpretation.

After deploy completes, capture the deploy id and the full result list. Surface succeeded/failed component counts.

### Step 4: Agentforce smoke gate (only when in scope)

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

### Step 4b: Playwright UI smoke gate (only when in scope)

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

### Step 5: Verify

After deploy + smoke gate, run a final verification:

```sh
# Confirm the deployed code matches what we built locally — list the latest deploy
sf project deploy report --target-org "$ALIAS" --json | jq '.result.status'

# Confirm a representative test still passes (smoke for non-Agentforce projects)
sf apex run test --target-org "$ALIAS" --test-level RunLocalTests --wait 10 --code-coverage --result-format json
```

Capture coverage. salesforce-rules.md mandates ≥75% — if coverage drops below the floor, flag it as a finding and recommend additional tests before promoting further.

### Step 6: Record state

If `pipeline-state.json` exists for the current REQ (we're inside `/proceed`):
1. Add a `canary` entry to `phaseHistory` with the result (passed/failed) per environment
2. Include: target org alias, deploy id, validate duration, test pass/fail count, agent test result, coverage %

Otherwise, just emit the report to stdout.

### Step 7: Auto-promote OR halt

- **Auto-promote** to the next environment in the ladder (sandbox → staging → prod) ONLY when `$ARGUMENTS` was omitted AND every gate passed.
- **Always halt** before attempting prod, even on auto-promote: emit a single line "Validate clean for prod. Run `/canary prod` to deploy." and stop. The prod deploy must be a deliberate, separate invocation — no automatic continuation through prod.

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
- Result: ✓ clean (or full error report on failure)

### Deploy (sandbox / staging only)
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
- Skipped (not @prod-safe): NNN  (only on prod runs)
- Trace artifacts: reports/playwright/<env>/
- Result: ✓ clean

### Verification
- Apex coverage: 78.4% (≥ 75% ✓)
- Final org status: <status>

Next step: <auto-promoted to staging | run `/canary prod` | halted because of <reason>>
```

## Failure modes

- **Validate fails**: stop. Surface the deployment errors verbatim. Do NOT attempt the deploy.
- **Deploy fails after validate succeeded**: rare (validate is server-side). Surface the failure; the corrective action is a forward-fix deploy, not a rollback.
- **Agentforce smoke fails**: stop before promoting further. Recommend investigation; do NOT auto-fix.
- **Playwright smoke fails**: stop before promoting further. Surface the failing spec, the path to the trace/video under `reports/playwright/$ENV/`, and the assertion message. Do NOT auto-fix; UI failures usually need the trace viewer (`npx playwright show-trace`) to diagnose.
- **Coverage drops below 75%**: surface as a Major finding; do NOT block promotion automatically (production policy may differ — let the user decide).

## What This Skill Does NOT Do

- Does NOT roll back. Salesforce has no revision-based rollback; the corrective action is a forward-fix deploy.
- Does NOT manage scratch orgs (use `sf org create scratch` directly).
- Does NOT modify metadata. It only validates, deploys, runs tests, and reports.
- Does NOT bypass `.claude/settings.json` ask-prompts. `sf project deploy start` and `sf agent activate` always prompt.
- Does NOT auto-promote to prod. Prod is always a deliberate, separate `/canary prod` invocation.
