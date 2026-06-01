# sf-skills — vendored from forcedotcom/afv-library

This directory is a **vendored copy** of [forcedotcom/afv-library](https://github.com/forcedotcom/afv-library) skill content. We track a pinned commit so behavior is reproducible across all consumer projects on this machine, even if upstream changes.

## Pinned commit

- **Repo**: https://github.com/forcedotcom/afv-library
- **Commit**: `302d11cc6a76bc1d7639ee69b89c6944b7f3f8fa`
- **Vendored**: 2026-06-01
- **Skills count**: 60

## License

afv-library is published under the BSD-3-Clause License. The full license text is in `LICENSE.txt` of the upstream repo. Vendoring preserves the per-skill `CREDITS.md` files where present.

## How to refresh

To re-vendor against a newer upstream commit:

```bash
# From a clean working tree
TMPDIR=$(mktemp -d)
git clone --depth 1 https://github.com/forcedotcom/afv-library.git "$TMPDIR/afv-library"
NEW_COMMIT=$(git -C "$TMPDIR/afv-library" rev-parse HEAD)

# Wipe the old vendored copy except this VENDORED.md and refresh
find skills/sf -mindepth 1 -maxdepth 1 ! -name VENDORED.md -exec rm -rf {} +
cp -r "$TMPDIR/afv-library/skills/"* skills/sf/

# Update the pinned commit above to $NEW_COMMIT, commit the bump
```

Run `python3 tools/lint-skills/check.py --root .` after refreshing — vendored skills should not trip the linter, and any drift in the SKILL.md frontmatter shape will surface here.

## What ADLC does with these skills

The 60 sf-skills are **rubrics**, not separately-dispatched agents. The ADLC review panel (correctness / quality / architecture / test-coverage / security) and the `task-implementer` load the relevant rubric at runtime by file glob — see `.adlc/context/sf-skills-catalog.md` for the catalog and the file-glob → skill mapping that powers the dispatch.

The `skills/sf-router/SKILL.md` orchestrator skill is the single entry point that other skills (`/proceed`, `/sprint`, `/architect`) consult to pick the right sf-skill for a given file or change set.
