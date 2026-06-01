# Presets

Stack-shaped starter configs for `.adlc/config.yml`. Each preset captures a common combination of Salesforce surface areas, deploy targets, and CI patterns. Pick the one closest to your scope, copy it into your repo, and replace the placeholder values.

## Available presets

| File | Scope |
|------|-------|
| [sfdc-core.yml](sfdc-core.yml) | Apex + LWC + Flow + SOQL + Permissions + Deploy. The right baseline for most Salesforce projects. |
| [sfdc-industries.yml](sfdc-industries.yml) | sfdc-core plus Data Cloud, Agentforce, OmniStudio, Industries CME EPC, and Vlocity build/deploy. Trim the `industries:` list to what's actually in scope. |

## How to use a preset

From inside the repo where you're running `/init`:

```bash
cp ~/.claude/skills/presets/sfdc-core.yml .adlc/config.yml
$EDITOR .adlc/config.yml
```

Replace every `<placeholder>` with a real value (project name, app prefix, sf CLI org aliases, package directories). Don't leave placeholders in — skills will fail loudly when they try to use them, but it's faster to just fill them in up front.

## What's a preset, exactly

A preset is **scope shape, not org configuration**. It declares:

- Which Salesforce surface areas are in play (`industries: [datacloud, agentforce, omnistudio, cme]`)
- Which sections are populated (e.g., `agentforce_variant`, `agentforce_test_specs` when Agentforce is in scope)
- Sensible defaults (e.g., `api_version: "66.0"` for Agentforce-enabled presets, `package_directories: ["force-app"]`)
- Example shape for the `repos:` and `orgs:` blocks

It does **not** contain:

- Real org IDs, sandbox URLs, sf CLI auth tokens, secrets
- Specific app prefixes or package names — leave those as placeholder strings
- Anything proprietary to a specific company's Salesforce setup

## Adding a new preset

If you have a Salesforce scope combination not covered here (e.g., MuleSoft-only, Marketing Cloud, Salesforce-with-Heroku-microservice), drop a new YAML file in this directory and update the table above. Naming convention: `sfdc-<scope>.yml` or `sfdc-<scope>-<sibling-tech>.yml`.

Open a PR against the canonical toolkit — presets benefit from being shared.
