#!/usr/bin/env python3
"""SKILL.md corruption + agent-policy linter — six orthogonal checks.

Run from the repo root:

    python3 tools/lint-skills/check.py [--root <path>]

Exit code: 0 on clean, otherwise min(num_findings, 255).

The six checks (each a pure ``(text, rel) -> list[Finding]`` except
``find_skill_files`` / ``find_agent_files``, the structural file finders):

1. ``check_sentinels``   — exact forbidden substrings from ``sentinels.txt``.
2. ``check_balance``     — ``$(``/``)`` and ``$((``/``))`` imbalance per fence.
3. ``check_posix_fence`` — ``local`` declaration inside an ``sh``/``shell`` fence.
4. ``check_cross_fence_fn`` — function defined in one fenced block but invoked
   only from a different fenced block in the same SKILL.md.
5. ``check_model_policy`` — under ``agents/*.md``, frontmatter ``model:``
   MUST be ``sonnet`` or ``opus``. ``haiku``/``TBD``/third-party models are
   policy violations per ``MODEL_ASSIGNMENTS.md``.
6. ``check_sf_checklist_source`` — advisory. A SKILL.md mentioning Salesforce
   artifacts but not sourcing ``partials/sf-quality-checklist.md`` is flagged.

``find_skill_files`` root-skip fix (REQ-436 ADR-5, executes REQ-433 ADR-3b's
deferred follow-up; LESSON-019 #2): the ``SKIP_DIR_PARTS`` membership test is
applied only to path components *strictly below* the resolved scan root, never
to the root's own components. Run from inside a ``.worktrees`` / ``.git`` /
``node_modules`` directory (every ``/proceed`` phase runs inside ``.worktrees``)
the linter previously scanned **zero** files and exited 0 — a confident green
having checked nothing. Now a root that itself sits under such a name is fully
scanned, while a descendant directory with one of those names is still skipped.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
SENTINELS_FILE = SCRIPT_DIR / "sentinels.txt"

SKIP_DIR_PARTS = {".git", ".worktrees", "node_modules"}

# Permitted model values in any agent's `model:` frontmatter. Anything else
# (haiku, kimi-k2.5, gpt-4, claude-3-5-sonnet, the literal placeholder TBD,
# etc.) is a project policy violation. Source: MODEL_ASSIGNMENTS.md.
ALLOWED_MODELS = frozenset({"sonnet", "opus"})

# SF-artifact triggers — a SKILL.md whose body mentions one of these globs is
# probably operating on Salesforce code and should source the quality checklist.
# Used by check_sf_checklist_source as an advisory hint, not as a hard gate.
SF_ARTIFACT_HINTS = (
    "*.cls",
    "*.trigger",
    "*.flow-meta.xml",
    "*.permissionset-meta.xml",
    "force-app/",
    "skills/sf/",
    "salesforce-rules.md",
    "sf-quality-checklist",
)
SF_CHECKLIST_SOURCE_MARKER = "partials/sf-quality-checklist.md"

FENCE_OPEN_RE = re.compile(r"^\s*```(sh|bash|shell)\b")
FENCE_CLOSE_RE = re.compile(r"^\s*```\s*$")

# REQ-436 ADR-6: a `local` declaration at statement position. Statement
# position = start of line, or after `;`, `&&`, `||`, `then`, `do`, or `{`.
# This deliberately does not match `local` as a substring of another word
# (e.g. `mylocal`, `local_var=`) — `\S` after the space ensures a declared
# name follows. Only applied to sh/shell fences (bash is exempt — see docstring).
POSIX_LOCAL_RE = re.compile(r"(?:^|;|&&|\|\||\bthen\b|\bdo\b|\{)\s*local\s+\S")

# REQ-436 ADR-7: a shell function definition `name() {` at statement position.
FN_DEF_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{")
# A statement-position invocation of a (separately-known) function name: the
# name as the first token of a body line, optionally followed by arguments.
# The name itself is captured so it can be checked against the known-defined
# set; this is intentionally conservative (no mid-line / piped invocations) to
# avoid false positives on prose that merely mentions the name.
FN_CALL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\b")


class Finding(NamedTuple):
    file: str
    line: int
    check: str
    message: str

    def format(self) -> str:
        return f"{self.file}:{self.line}: {self.check}: {self.message}"


def find_skill_files(root: Path) -> Iterable[Path]:
    root_resolved = root.resolve()
    for path in root.rglob("SKILL.md"):
        # Symlinks may point outside the scan root — defend against
        # following them out of the tree (unchanged guard).
        try:
            resolved = path.resolve()
            rel = resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            continue
        # REQ-436 ADR-5 (executes REQ-433 ADR-3b; LESSON-019 #2): apply the
        # skip list ONLY to path components strictly BELOW the resolved root —
        # never to the root's own components. A descendant directory named
        # `.git`/`.worktrees`/`node_modules` is still skipped; a root that
        # itself sits under such a name is still fully scanned (the
        # `/proceed`-runs-inside-`.worktrees` vacuous-walk false-green).
        # rel.parts excludes the root and includes the trailing "SKILL.md";
        # the directory components to test are everything but that last part.
        if any(part in SKIP_DIR_PARTS for part in rel.parts[:-1]):
            continue
        yield path


def load_sentinels(path: Path) -> list[str]:
    if not path.is_file():
        return []
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def check_sentinels(text: str, sentinels: list[str], rel: str) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for sentinel in sentinels:
            if sentinel in line:
                findings.append(
                    Finding(rel, lineno, "sentinel",
                            f"matches forbidden sentinel '{sentinel}'")
                )
    return findings


def _count_balance(fence_body: str) -> tuple[int, int]:
    """Return (single_deficit, double_deficit) for a fence body.

    The REQ-424 corruption shape is "an opening `$(` whose closing `)` was
    removed." A precise paren-matcher over shell text gets defeated by valid
    nesting like `$(( ($(x) - y) ))` — literal `(...)` groups inside
    arithmetic substitution. Instead, count raw substring occurrences and
    project them into orthogonal buckets:

      raw_single_open  = count('$(')          # overcounts: $(( contains $(
      raw_single_close = count(')')           # overcounts: )) contains two )
      double_open      = count('$((')
      double_close     = count('))')

      single_open  = raw_single_open  - double_open
      single_close = raw_single_close - 2 * double_close

      single_deficit = max(0, single_open  - single_close)
      double_deficit = max(0, double_open  - double_close)

    Only the failure direction (deficit > 0) is reported — the REQ-424
    shape is missing closes, and unbalanced extra `)` in shell prose is
    common (e.g., end of a `case` arm) and not worth flagging.
    """
    raw_single_open = fence_body.count("$(")
    raw_single_close = fence_body.count(")")
    double_open = fence_body.count("$((")
    double_close = fence_body.count("))")
    single_open = raw_single_open - double_open
    single_close = raw_single_close - 2 * double_close
    return (
        max(0, single_open - single_close),
        max(0, double_open - double_close),
    )


def check_balance(text: str, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fence_start = i + 1
        i += 1
        body_lines: list[str] = []
        while i < len(lines) and not FENCE_CLOSE_RE.match(lines[i]):
            body_lines.append(lines[i])
            i += 1
        if i >= len(lines):
            findings.append(
                Finding(rel, fence_start, "balance",
                        f"fence at line {fence_start} — unclosed (no ``` before EOF)")
            )
            break
        body = "\n".join(body_lines)
        single_deficit, double_deficit = _count_balance(body)
        if single_deficit:
            findings.append(
                Finding(rel, fence_start, "balance",
                        f"fence at line {fence_start} — '$(' opens exceed ')' closes by {single_deficit}")
            )
        if double_deficit:
            findings.append(
                Finding(rel, fence_start, "balance",
                        f"fence at line {fence_start} — '$((' opens exceed '))' closes by {double_deficit}")
            )
        i += 1
    return findings


def _iter_fences(text: str):
    """Yield ``(lang, fence_index, body_start_lineno, [(lineno, line), ...])``
    for each fenced shell block (``sh``/``bash``/``shell``).

    ``body_start_lineno`` is the absolute 1-based line of the first body line.
    ``fence_index`` is a 0-based ordinal across the file's shell fences (used
    by ``check_cross_fence_fn`` to tell "same fence" from "different fence").
    Reuses the same open/close machinery as ``check_balance``; an unclosed
    fence is left to ``check_balance`` to report — here we simply consume to
    EOF so the other checks still see its body.
    """
    lines = text.splitlines()
    i = 0
    fence_index = -1
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fence_index += 1
        lang = m.group(1)
        body_start = i + 2  # 1-based line number of the first body line
        i += 1
        body: list[tuple[int, str]] = []
        while i < len(lines) and not FENCE_CLOSE_RE.match(lines[i]):
            body.append((i + 1, lines[i]))
            i += 1
        yield lang, fence_index, body_start, body
        i += 1  # step past the closing ``` (or past EOF — loop then ends)


def check_posix_fence(text: str, rel: str) -> list[Finding]:
    """REQ-436 ADR-6: flag a ``local`` declaration inside an ``sh``/``shell``
    fence. ``bash`` fences are EXEMPT by design — many ``bash`` builds support
    ``local``; conventions.md's POSIX-only mandate targets ``sh``/``shell``, so
    flagging ``bash`` would false-positive in legitimately-``bash`` blocks.
    The reported line is the absolute line of the offending body line (NOT the
    fence-open line) so ``/analyze`` Step 1.9's ``<file>:<line>:`` parser stays
    accurate.
    """
    findings: list[Finding] = []
    for lang, _idx, _start, body in _iter_fences(text):
        if lang not in ("sh", "shell"):
            continue
        for lineno, line in body:
            if POSIX_LOCAL_RE.search(line):
                findings.append(
                    Finding(
                        rel, lineno, "posix-fence",
                        "'local' is not POSIX in a ```sh fence — use "
                        "uniquely-prefixed globals or relabel the fence ```bash",
                    )
                )
    return findings


def check_cross_fence_fn(text: str, rel: str) -> list[Finding]:
    """REQ-436 ADR-7: flag a shell function DEFINED in one fenced block but
    INVOKED only from a DIFFERENT fenced block in the same SKILL.md. SKILL.md
    fenced blocks do not share shell state across steps, so the function is
    undefined at that call site (the Defect-1 silent-telemetry-loss class).

    Conservative against false positives: a name is only considered if it is
    both *defined* with the ``() {`` form AND *invoked* at statement position
    within some fence; prose mentions outside fences are ignored. A
    define-and-use within the same fence is legitimate and never flagged
    (shell state is shared *within* a single fenced block).
    """
    fences = list(_iter_fences(text))

    # First pass: every function name defined anywhere (with its defining
    # fence index and def line — first definition wins for reporting).
    defs: dict[str, tuple[int, int]] = {}  # name -> (fence_index, def_lineno)
    for _lang, idx, _start, body in fences:
        for lineno, line in body:
            dm = FN_DEF_RE.match(line)
            if dm:
                name = dm.group(1)
                if name not in defs:
                    defs[name] = (idx, lineno)

    if not defs:
        return []

    # Second pass: statement-position invocations of any defined name. A line
    # that is itself a definition of that name is not an invocation of it.
    # invokes[name] = set of (fence_index, lineno)
    invokes: dict[str, list[tuple[int, int]]] = {name: [] for name in defs}
    for _lang, idx, _start, body in fences:
        for lineno, line in body:
            cm = FN_CALL_RE.match(line)
            if not cm:
                continue
            name = cm.group(1)
            if name not in defs:
                continue
            if FN_DEF_RE.match(line):
                continue  # this line defines the fn; not an invocation
            invokes[name].append((idx, lineno))

    findings: list[Finding] = []
    for name, (def_idx, def_lineno) in defs.items():
        calls = invokes[name]
        if not calls:
            continue  # defined but never invoked anywhere — out of scope here
        if any(c_idx == def_idx for c_idx, _ in calls):
            continue  # invoked in its own defining fence → legitimate
        # Invoked only in fence(s) other than the one it is defined in.
        inv_idx, inv_lineno = calls[0]
        findings.append(
            Finding(
                rel, def_lineno, "cross-fence-fn",
                f"'{name}' defined in fenced block at line {def_lineno} but "
                f"invoked at line {inv_lineno} in a different fenced block — "
                "SKILL.md fenced blocks do not share shell state; move it to "
                "a sourced partial",
            )
        )
    return findings


def _safe_label(skill_path: Path, root: Path) -> str:
    """Non-leaking finding label for ``skill_path``.

    Findings are printed to stdout and land in CI logs, so the label must
    never be an absolute filesystem path (BUG-054; REQ-435 verify Low #1/#2).
    Root-relative when ``skill_path`` is under ``root``; basename fallback
    otherwise. ``Path.relative_to`` is pure path arithmetic and raises only
    ``ValueError`` (never ``OSError``), so the narrow except is exact. Applied
    at *every* leak point in ``run()``, not just the main one (LESSON-007).
    """
    try:
        return str(skill_path.relative_to(root))
    except ValueError:
        return skill_path.name


def find_agent_files(root: Path) -> Iterable[Path]:
    """Yield every agent definition under <root>/agents/*.md, applying the
    same SKIP_DIR_PARTS guard as find_skill_files.
    """
    agents_dir = root / "agents"
    if not agents_dir.is_dir():
        return
    root_resolved = root.resolve()
    for path in agents_dir.glob("*.md"):
        if not path.is_file():
            continue
        try:
            resolved = path.resolve()
            rel = resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            continue
        if any(part in SKIP_DIR_PARTS for part in rel.parts[:-1]):
            continue
        yield path


# `model:` frontmatter line — captures the value (lowercase, no quotes).
MODEL_LINE_RE = re.compile(r"^\s*model\s*:\s*([A-Za-z0-9_.-]+)", re.MULTILINE)


def check_model_policy(text: str, rel: str) -> list[Finding]:
    """Verify that an agent's `model:` frontmatter is one of the permitted
    values. The toolkit enforces Sonnet/Opus only; everything else is a
    policy violation (haiku, kimi-k2.5, third-party models, the literal
    placeholder `TBD`).

    Only inspects the YAML frontmatter (the leading `---`-delimited block).
    A model line OUTSIDE the frontmatter (e.g., in prose) is ignored.
    """
    findings: list[Finding] = []
    # Restrict to the leading frontmatter block.
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not fm_match:
        return findings
    fm_text = fm_match.group(1)
    for m in MODEL_LINE_RE.finditer(fm_text):
        value = m.group(1)
        if value.lower() in ALLOWED_MODELS:
            continue
        # Resolve the absolute line number within the file (frontmatter starts at line 2).
        line_no = fm_text[: m.start()].count("\n") + 2
        findings.append(
            Finding(rel, line_no, "model-policy",
                    f"agent model '{value}' is not permitted — use 'sonnet' or 'opus' "
                    f"(see MODEL_ASSIGNMENTS.md). 'TBD'/'haiku'/third-party models are policy violations.")
        )
    return findings


def check_sf_checklist_source(text: str, rel: str) -> list[Finding]:
    """Advisory: a SKILL.md that operates on Salesforce code (mentions Apex /
    Flow / LWC / permission set globs OR `force-app/` paths OR the salesforce
    rules) should source `partials/sf-quality-checklist.md` so the implementer
    and reviewers see the always-on baseline.

    Reports at most one finding per SKILL.md so a long skill doesn't get
    flagged repeatedly. Skipped on the catalog and the rules document itself
    (which are the source-of-truth files, not consumers).
    """
    # Don't flag the catalog / rules / checklist themselves.
    rel_lower = rel.lower()
    if any(s in rel_lower for s in (
        "sf-skills-catalog.md",
        "salesforce-rules.md",
        "sf-quality-checklist.md",
    )):
        return []
    # Only fire on SKILL.md files (this check is for the active skills, not the
    # vendored sf-skills which are content-as-rubric, not orchestrators).
    if not rel.endswith("SKILL.md"):
        return []
    # Skip the vendored sf-skills set — they ARE the rubrics; they don't source
    # the checklist, the checklist references them.
    if "/sf/" in rel.replace("\\", "/"):
        return []
    if not any(hint in text for hint in SF_ARTIFACT_HINTS):
        return []
    if SF_CHECKLIST_SOURCE_MARKER in text:
        return []
    return [
        Finding(rel, 1, "sf-checklist-source",
                "SKILL.md mentions Salesforce artifacts but does not source partials/sf-quality-checklist.md "
                "(the always-on baseline). Add `!`cat .adlc/partials/sf-quality-checklist.md ...`` "
                "under Context, or read it explicitly in the relevant step.")
    ]


def run(root: Path) -> list[Finding]:
    sentinels = load_sentinels(SENTINELS_FILE)
    findings: list[Finding] = []

    for skill_path in find_skill_files(root):
        # Compute the non-leaking label BEFORE the read so the io-error
        # branch can use it too (BUG-054 — was `str(skill_path)`).
        rel = _safe_label(skill_path, root)
        try:
            text = skill_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(
                Finding(rel, 1, "io-error",
                        f"could not read: {exc.strerror or 'I/O error'}")
            )
            continue
        findings.extend(check_sentinels(text, sentinels, rel))
        findings.extend(check_balance(text, rel))
        findings.extend(check_posix_fence(text, rel))
        findings.extend(check_cross_fence_fn(text, rel))
        findings.extend(check_sf_checklist_source(text, rel))

    # Agent files: enforce model-policy (Sonnet/Opus only).
    for agent_path in find_agent_files(root):
        rel = _safe_label(agent_path, root)
        try:
            text = agent_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(
                Finding(rel, 1, "io-error",
                        f"could not read: {exc.strerror or 'I/O error'}")
            )
            continue
        findings.extend(check_model_policy(text, rel))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="root to scan (default: .)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    findings = run(root)
    for f in findings:
        print(f.format())
    if findings:
        print(f"skill-md-corruption: {len(findings)} findings", file=sys.stderr)
    return min(len(findings), 255)


if __name__ == "__main__":
    sys.exit(main())
