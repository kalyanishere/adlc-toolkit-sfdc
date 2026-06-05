# Playwright harness — Salesforce template

This directory is a self-contained Playwright harness that `/init` Step 11
copies into a consumer repo. After scaffolding, the layout in the consumer
repo is:

```
<repo-root>/
  playwright.config.ts                # this file (verbatim copy)
  tests/e2e/
    global-setup.ts                   # Salesforce front-door auth → storageState
    example.spec.ts.example           # rename to `<feature>.spec.ts` to use
    .gitignore                        # ignores storageState.json
```

The harness satisfies every gate in `agents/test-auditor.md`:

| Severity guard | How it's satisfied |
|---|---|
| Critical: hardcoded credentials | Auth comes from `sf org display`, never inline |
| Critical: prod project mutates org | `prod` project has `grep: /@prod-safe/` |
| Critical: `storageState.json` not gitignored | `tests/e2e/.gitignore` ignores it |
| Major: missing `globalSetup` | Wired in `playwright.config.ts` |
| Major: missing `retries` for CI | `retries: process.env.CI ? 1 : 0` |
| Major: hard sleeps | Example spec uses only web-first auto-waiting |
| Major: brittle selectors | Example spec uses `getByRole`/`getByLabel`/`getByTestId` |
| Minor: missing `test:e2e` script | `/init` Step 11 advises adding it to `package.json` |

## How specs authenticate

`global-setup.ts` runs once before any spec:

1. If `/canary` set `PLAYWRIGHT_LOGIN_URL_FILE`, the global setup reads the
   front-door URL written by `sf org open --url-only --json` and seeds the
   cookie jar from there.
2. Otherwise it reads `orgs.<project-name>` from `.adlc/config.yml` (or
   `SF_TARGET_ORG`), runs `sf org display --target-org <alias> --json`, and
   visits `<instance>/secur/frontdoor.jsp?sid=<token>` to seed the cookie.

Either path produces `tests/e2e/storageState.json`, which every spec then
reuses via `use.storageState` in `playwright.config.ts`.

## Running specs

Local sandbox:

```bash
npm run test:e2e -- --project=sandbox
```

CI / staging:

```bash
SF_TARGET_ORG=$STAGING_ALIAS npm run test:e2e -- --project=staging
```

Prod smoke (read-only specs only — `grep: /@prod-safe/` filter):

```bash
SF_TARGET_ORG=$PROD_ALIAS npx playwright test --project=prod
```

## When `/canary` runs the harness

`/canary` Step 4b runs the same suite as a real-browser smoke gate after
each environment validates. Trace artifacts land in
`reports/playwright/<env>/`. On failure, `/canary` halts and refuses to
promote to the next environment.
