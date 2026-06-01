# Clean SKILL.md fixture — no findings expected

This file exists only to verify the linter does not false-positive on a
benign skill.

```sh
echo "balanced $(date -u +%s)"
```

```bash
total=$(( 1 + 2 ))
echo $total
```

A benign SKILL.md — no sentinels, balanced fences, no cross-fence functions.
