# sf-preflight — local Salesforce metadata pre-flight checks

Catches deploy failures locally in seconds, before paying 60-90s per `sf project deploy validate` round trip.

## Checks

| Check | Script | Org-aware? | Wired into |
|---|---|---|---|
| `permsets` | `check-permsets.mjs` | yes (Tooling API → EntityDefinition) | `generating-permission-set/SKILL.md`, `/canary` Step 2a |
| `metadata` (REQ-F) | `check-metadata.mjs` | no (workspace cross-reference) | `/canary` Step 2a |

## Usage

```sh
# Perm-set policy: forbid <fieldPermissions>, require viewAllFields/editAllFields, verify objects exist
sh tools/sf-preflight/check.sh permsets --workspace force-app --target-org my-sandbox

# Same, offline (XML structure only — no Tooling API)
sh tools/sf-preflight/check.sh permsets --workspace force-app --offline

# Cross-reference (perm-set → Apex class, layout → field, FlexiPage → object, …)
sh tools/sf-preflight/check.sh metadata --workspace force-app

# Either, machine-readable
sh tools/sf-preflight/check.sh permsets --workspace force-app --offline --json
```

## Exit codes

- `0` — clean
- `1` — at least one BLOCK finding (failure)
- `2` — invocation error (bad args, missing org, etc.)

WARN-level findings (e.g. cross-package object references, missing-custom-field on a layout) print but do not change the exit code — they are often false positives when the workspace is a partial slice of a larger package.

## Cache

Org existence-check responses are cached at `.adlc/.cache/org-objects.<alias>.json` for the run. Delete the file to force a refresh.

## Adding a new check

1. Add a `check-<name>.mjs` script that takes `--workspace` and (if needed) `--target-org`, supports `--json` and `--offline`, and exits 0/1/2 per the contract above.
2. Wire it into `check.sh`'s `case "$CHECK"` block.
3. Wire it into the relevant skill (perm-set authoring, `/canary` Step 2a, etc.) and document the gate in `salesforce-rules.md` or `conventions.md`.
4. Add a smoke test under `tests/` (offline mode, synthetic fixtures).
