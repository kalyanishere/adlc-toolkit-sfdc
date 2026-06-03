---
id: TASK-xxx
title: "Task Title"
status: draft
parent: REQ-xxx
created: YYYY-MM-DD
updated: YYYY-MM-DD
dependencies: []
required_skills: []   # sf-skill names the implementer MUST load via the Skill tool BEFORE editing files.
                      # Populated by /architect from .adlc/context/sf-skills-catalog.md based on the
                      # touched-file globs. Example: [building-ui-bundle-app, generating-ui-bundle-metadata].
                      # When empty AND the task touches metadata under salesforce.workspace (e.g. force-app/),
                      # task-implementer surfaces a "no skill declared — proceeding from first principles" warning.
# repo: <repo-id>   # REQUIRED in cross-repo projects (see .adlc/config.yml).
                    # One of the ids under `repos:` in .adlc/config.yml.
                    # In single-repo projects, omit or set to the primary repo id.
---

## Description

What this task accomplishes.

## Files to Create/Modify

- `path/to/file.js` — description of changes

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Technical Notes

Implementation details, patterns to follow, edge cases.
