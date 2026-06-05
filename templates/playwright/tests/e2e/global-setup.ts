// tests/e2e/global-setup.ts — Salesforce Playwright global setup
//
// Reads the target org via `sf org display --target-org <alias> --json`,
// persists the front-door session URL into storageState.json, and exports
// PLAYWRIGHT_BASE_URL for the spec runtime.
//
// agents/test-auditor.md requires this file for any project declaring
// `playwright_specs:`. Without it, storageState writes never run and every
// spec fails on its first navigation.
//
// Auth resolution order:
//   1. PLAYWRIGHT_BASE_URL + PLAYWRIGHT_LOGIN_URL_FILE env vars (set by /canary)
//   2. .adlc/config.yml `orgs.<env>` alias (env from --project)
//   3. SF_TARGET_ORG env var
//
// Never put credentials inline in this file or any spec — auth must come
// from `sf org display`.

import { chromium, FullConfig, request } from '@playwright/test';
import { execSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname } from 'node:path';

type SfOrgDisplay = {
  result: {
    instanceUrl: string;
    username: string;
    accessToken: string;
  };
};

function readOrgAlias(projectName: string | undefined): string | undefined {
  // /canary writes the front-door URL to a JSON file; prefer that when present.
  const fromFile = process.env.PLAYWRIGHT_LOGIN_URL_FILE;
  if (fromFile && existsSync(fromFile)) return undefined;

  // Otherwise resolve from .adlc/config.yml. Hand-rolled YAML grep keeps this
  // dependency-free; the orgs: block is a flat map.
  if (existsSync('.adlc/config.yml')) {
    const yml = readFileSync('.adlc/config.yml', 'utf8');
    const orgsBlock = yml.match(/^orgs:\s*\n((?:\s+\S.*\n?)+)/m)?.[1] ?? '';
    const lookup = (key: string) =>
      orgsBlock.match(new RegExp(`^\\s+${key}:\\s*"?([^"\\n#]+)"?`, 'm'))?.[1]?.trim();
    const alias =
      (projectName && lookup(projectName)) ||
      lookup('sandbox') ||
      process.env.SF_TARGET_ORG;
    return alias;
  }
  return process.env.SF_TARGET_ORG;
}

function sfOrgDisplay(alias: string): SfOrgDisplay {
  const json = execSync(`sf org display --target-org "${alias}" --json`, {
    encoding: 'utf8',
  });
  return JSON.parse(json) as SfOrgDisplay;
}

async function persistStorageState(
  instanceUrl: string,
  accessToken: string,
  storageStatePath: string,
) {
  // Front-door login: GET /secur/frontdoor.jsp?sid=<token> sets the session
  // cookie on the org instance. We capture the cookie and persist it.
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  const frontDoor = `${instanceUrl}/secur/frontdoor.jsp?sid=${accessToken}`;
  await page.goto(frontDoor, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});

  mkdirSync(dirname(storageStatePath), { recursive: true });
  await context.storageState({ path: storageStatePath });
  await browser.close();
}

export default async function globalSetup(config: FullConfig) {
  const project = config.projects[0]?.name;
  const storageStatePath = 'tests/e2e/storageState.json';

  // /canary path: PLAYWRIGHT_BASE_URL + PLAYWRIGHT_LOGIN_URL_FILE already set.
  const loginUrlFile = process.env.PLAYWRIGHT_LOGIN_URL_FILE;
  if (loginUrlFile && existsSync(loginUrlFile)) {
    const { result } = JSON.parse(readFileSync(loginUrlFile, 'utf8'));
    process.env.PLAYWRIGHT_BASE_URL ||= result.url;
    // /canary's `sf org open --url-only` produces a single-use front-door URL.
    // Visit it to seed the cookie jar.
    const browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(result.url, { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});
    mkdirSync(dirname(storageStatePath), { recursive: true });
    await context.storageState({ path: storageStatePath });
    await browser.close();
    return;
  }

  // Local dev / CI path: derive alias from .adlc/config.yml or SF_TARGET_ORG.
  const alias = readOrgAlias(project);
  if (!alias) {
    throw new Error(
      'global-setup: no Salesforce org alias found. Set SF_TARGET_ORG or declare ' +
        '`orgs.<project>` in .adlc/config.yml. Never inline credentials in specs.',
    );
  }

  const { result } = sfOrgDisplay(alias);
  process.env.PLAYWRIGHT_BASE_URL ||= result.instanceUrl;
  await persistStorageState(result.instanceUrl, result.accessToken, storageStatePath);
}
