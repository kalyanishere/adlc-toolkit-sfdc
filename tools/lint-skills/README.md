# tools/lint-skills — SKILL.md corruption lint

A small offline linter that catches the class of failures that escaped REQ-424
verify: literal-but-broken shell constructs embedded in skill prose. It is NOT
a general markdown linter and NOT a general shell linter.

## What it checks

1. **Sentinel literals** — exact substrings listed in `sentinels.txt` should
   never appear in any `SKILL.md`. Seeded with the REQ-424 corruption
   sequence; one line per known-bad pattern.
2. **Shell-construct balance** — within each ` ```sh `, ` ```bash `, or
   ` ```shell ` fenced block, the linter counts `$(` vs `)` and `$((` vs
   `))`. Imbalance is a finding. Outside-fence text is ignored (skill prose
   may legitimately use unbalanced examples).
3. **POSIX-fence (`local` in an `sh`/`shell` fence)** — within a ` ```sh ` or
   ` ```shell ` fenced block, any `local ` declaration at statement position
   (start of line, or after `;`, `&&`, `||`, `then`, `do`, `{`) is a finding.
   `local` is not POSIX; `conventions.md`'s "Bash in skills" mandates
   POSIX-only shell. **` ```bash ` fences are exempt by design (REQ-436
   ADR-6):** many `bash` builds support `local`, and the POSIX-only mandate
   targets `sh`/`shell`, so flagging `bash` would be a false positive in
   legitimately-`bash` blocks. The reported line is the absolute line of the
   offending body line (not the fence-open), so `/analyze` Step 1.9's
   `<file>:<line>:` parser stays accurate.
4. **Cross-fence function (`cross-fence-fn`)** — a shell function *defined*
   inside one fenced block but *invoked* only from a *different* fenced block
   in the same SKILL.md is a finding. SKILL.md fenced blocks do not share
   shell state across steps, so the function is undefined at that call site
   (silent `command not found`, swallowed telemetry). The fix is to move the
   function into a sourced partial and source it in the same fenced block as
   the call. Conservative against false positives: only names that are both
   *defined* with the `name() {` form **and** *invoked* at statement position
   within a fence are considered; prose mentions outside fences are ignored,
   and a define-and-use within the *same* fence is legitimate (never flagged).
5. **Model policy (`model-policy`)** — under `agents/*.md`, the YAML
   frontmatter `model:` value MUST be one of `sonnet` or `opus`. Anything
   else (`haiku`, third-party model names, the literal placeholder `TBD`)
   is a project policy violation per `MODEL_ASSIGNMENTS.md`. Only the leading
   frontmatter block is inspected; mentions of model names in prose body are
   ignored. The agent-only rule does not run against `<skill>/SKILL.md` files.
6. **SF checklist source (`sf-checklist-source`)** — advisory. A SKILL.md
   that mentions Salesforce artifacts (`*.cls`, `*.trigger`, `*.flow-meta.xml`,
   `*.permissionset-meta.xml`, `force-app/`, or `salesforce-rules.md`) but does
   NOT source `partials/sf-quality-checklist.md` is flagged with one finding.
   The catalog (`sf-skills-catalog.md`), the rules document
   (`salesforce-rules.md`), the checklist itself, and every vendored sf-skill
   under `skills/sf/` are excluded — those are content-as-rubric, not
   orchestrators. Reports at most one finding per SKILL.md.

## Usage

```sh
# From the repo root
python3 tools/lint-skills/check.py
# or
sh tools/lint-skills/check.sh
```

Exit code is `0` on a clean pass, otherwise `min(findings, 255)`. Findings are
written to stdout in the format `<file>:<line>: <check-name>: <message>`.

`/analyze` runs the same check at Step 1.9 and surfaces results as a
`skill-md-corruption` audit dimension.

## Adding a new sentinel

A new corruption shape escaped detection? Append one literal line to
`sentinels.txt`. Comments (`#`-prefixed) and blank lines are ignored. The
linter picks up the new sentinel on its next run — no code changes needed.

## Tests

```sh
pytest tools/lint-skills/tests/ -q
```

## Constraints

- Python 3 stdlib only (`argparse`, `re`, `pathlib`, `sys`). No third-party
  packages. No network.
- POSIX `sh`-compatible wrapper. Tested on macOS and Linux.
- Read-only against the repo. No temp files, no logs, no cache.
