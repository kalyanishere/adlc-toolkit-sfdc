#!/usr/bin/env python3
"""sf-lint — Salesforce-rules static checker (subset).

Run from the repo root:

    python3 tools/sf-lint/check.py [--root <path>]

Exit code: 0 on clean, otherwise min(num_findings, 255).

Catches the static-checkable subset of `partials/sf-quality-checklist.md`
(Apex baseline, Governor limits, Security, Permissions, Prohibited Practices).
Anything requiring semantic understanding (newspaper rule, Builder pattern,
ApexDoc completeness) is review-only and lives in `agents/quality-reviewer.md`.

Checks (each is a pure ``(text, rel) -> list[Finding]``):

1. ``check_sharing_keyword``      — Apex class declared without `with sharing` /
                                    `without sharing` / `inherited sharing`.
2. ``check_access_level``         — SOQL/DML without an explicit `AccessLevel`
                                    or `WITH USER_MODE`/`WITH SYSTEM_MODE`.
3. ``check_no_future``            — `@future` annotation anywhere in Apex.
4. ``check_no_seealldata``        — `SeeAllData=true` in any test annotation.
5. ``check_soql_dml_in_loop``     — SOQL `[SELECT ...]` or DML statement inside
                                    a `for` loop body.
6. ``check_hardcoded_id``         — 15- or 18-char Salesforce ID literal in
                                    Apex source.
7. ``check_hardcoded_url``        — `https://*.salesforce.com` (or `force.com`)
                                    URL literal in Apex source.
8. ``check_perm_set_naming``      — Permission set file name does not match
                                    `[AppPrefix]_[Component]_[AccessLevel]`
                                    where AccessLevel ∈ {Read,Write,Full,
                                    Execute,Admin}.
9. ``check_perm_set_anti_patterns`` — `viewAllData`/`modifyAllData` enabled in
                                      a permission set.
10. ``check_apex_doc_present``    — public class / public method without an
                                    immediately-preceding ApexDoc block.
                                    (Heuristic — coarse but catches the bulk.)

This linter is deliberately substring/regex based — no shell parsing, no
real Apex parser. Coverage is the static-checkable subset; semantic checks
are out of scope by design.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent

SKIP_DIR_PARTS = {".git", ".worktrees", "node_modules", "skills"}  # skill dirs are vendored content
SKIP_FILE_SUFFIXES = (".md",)  # don't lint markdown documentation


class Finding(NamedTuple):
    rel: str
    line: int
    rule: str
    message: str

    def format(self) -> str:
        return f"{self.rel}:{self.line}: {self.rule}: {self.message}"


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _is_skip_dir(parts: tuple[str, ...]) -> bool:
    return any(p in SKIP_DIR_PARTS for p in parts)


def find_apex_files(root: Path) -> list[Path]:
    """Return every .cls and .trigger under root, excluding SKIP_DIR_PARTS."""
    out = []
    root_resolved = root.resolve()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if not (p.suffix in (".cls", ".trigger")):
            continue
        # Path components STRICTLY below root (not the root's own parts) are checked.
        try:
            rel_parts = p.resolve().relative_to(root_resolved).parts
        except (OSError, ValueError):
            continue
        if _is_skip_dir(rel_parts[:-1]):  # exclude the file's own basename
            continue
        out.append(p)
    return out


def find_permset_files(root: Path) -> list[Path]:
    """Return every .permissionset-meta.xml under root, excluding SKIP_DIR_PARTS."""
    out = []
    root_resolved = root.resolve()
    for p in root.rglob("*.permissionset-meta.xml"):
        if not p.is_file():
            continue
        try:
            rel_parts = p.resolve().relative_to(root_resolved).parts
        except (OSError, ValueError):
            continue
        if _is_skip_dir(rel_parts[:-1]):
            continue
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# Apex checks
# ---------------------------------------------------------------------------

# A class declaration line — captures the modifiers + 'class' + name.
# Handles: public/global/private ± with/without/inherited sharing ± virtual/abstract.
CLASS_DECL_RE = re.compile(
    r"^\s*(?:@[\w.]+(?:\([^)]*\))?\s+)*"            # leading @annotations
    r"(?:global|public|private|protected)\s+"        # access modifier (required for top-level)
    r"(?:(?:virtual|abstract|with\s+sharing|without\s+sharing|inherited\s+sharing)\s+)*"
    r"class\s+([A-Za-z_][A-Za-z0-9_]*)\b",
    re.MULTILINE,
)

# Capture the modifier set so we can assert sharing keyword presence.
CLASS_LINE_RE = re.compile(
    r"^(\s*)(?:@[\w.]+(?:\([^)]*\))?\s*\n)*\s*"
    r"((?:global|public|private|protected)\s+(?:[\w\s]+?))\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b",
    re.MULTILINE,
)


def check_sharing_keyword(text: str, rel: str) -> list[Finding]:
    """Find class declarations missing an explicit sharing keyword.

    Inner classes inherit sharing from their outer class; we only check the
    outermost (column-0) declarations.
    """
    findings: list[Finding] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # Only top-level (no leading whitespace) declarations
        if not re.match(r"^(?:@[\w.]+\s+)*(?:global|public|private|protected)\s+", line):
            continue
        m = re.match(
            r"^\s*((?:@[\w.]+(?:\([^)]*\))?\s+)*)"
            r"((?:global|public|private|protected)(?:\s+(?:virtual|abstract|with\s+sharing|without\s+sharing|inherited\s+sharing))*)"
            r"\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\b",
            line,
        )
        if not m:
            continue
        modifiers = m.group(2)
        if re.search(r"\b(with|without|inherited)\s+sharing\b", modifiers):
            continue
        findings.append(
            Finding(rel, i + 1, "sharing-keyword",
                    f"class '{m.group(3)}' has no explicit 'with sharing' / 'without sharing' / 'inherited sharing'")
        )
    return findings


# SOQL inline query: [SELECT ... FROM ... ]. Match the opening bracket + SELECT.
SOQL_INLINE_RE = re.compile(r"\[\s*SELECT\b", re.IGNORECASE)
# DML statements at statement position.
DML_STMT_RE = re.compile(
    r"\b(?:Database\.(?:insert|update|upsert|delete|undelete|merge)|insert|update|upsert|delete|undelete|merge)\b",
    re.IGNORECASE,
)
ACCESS_LEVEL_RE = re.compile(r"\bAccessLevel\.(?:USER_MODE|SYSTEM_MODE)\b", re.IGNORECASE)
WITH_MODE_RE = re.compile(r"\bWITH\s+(?:USER_MODE|SYSTEM_MODE)\b", re.IGNORECASE)


def check_access_level(text: str, rel: str) -> list[Finding]:
    """Flag SOQL or DML statements without explicit AccessLevel / WITH MODE.

    Heuristic: scan each line; if it contains a DML keyword OR an inline SOQL
    bracket, require ACCESS_LEVEL_RE (for DML) or WITH_MODE_RE (for SOQL) to
    appear within the same logical statement (3-line lookahead window).
    """
    findings: list[Finding] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue

        # Inline SOQL: [SELECT ...]
        if SOQL_INLINE_RE.search(line):
            window = "\n".join(lines[i: min(i + 3, len(lines))])
            if not WITH_MODE_RE.search(window):
                # Skip when the SOQL is in test code (Test classes often query without USER_MODE for setup)
                # — heuristic: file ends with Test.cls / _Test.cls
                if not (rel.endswith("Test.cls") or rel.endswith("_Test.cls") or rel.startswith("Test_") or "/Test_" in rel):
                    findings.append(
                        Finding(rel, i + 1, "access-level",
                                "SOQL inline query without WITH USER_MODE / WITH SYSTEM_MODE")
                    )

        # DML — but be careful: 'update' / 'delete' are common English words in comments
        # and can appear in identifiers; only flag when DML_STMT_RE matches at statement position
        # AND no AccessLevel reference is in the surrounding window.
        if DML_STMT_RE.search(line):
            # Statement-position DML: line ends with a semicolon OR the keyword is followed by an identifier OR list literal
            if re.search(r"\b(insert|update|upsert|delete|undelete|merge|Database\.\w+)\s*[\(\w]", line, re.IGNORECASE):
                window = "\n".join(lines[max(0, i - 1): min(i + 3, len(lines))])
                if not ACCESS_LEVEL_RE.search(window) and not WITH_MODE_RE.search(window):
                    if not (rel.endswith("Test.cls") or rel.endswith("_Test.cls") or rel.startswith("Test_") or "/Test_" in rel):
                        # Skip when 'update' is clearly an English word in a string/comment context
                        if not re.search(r'"[^"]*\b(insert|update|upsert|delete|undelete|merge)\b[^"]*"', line, re.IGNORECASE) \
                           and not re.search(r"'[^']*\b(insert|update|upsert|delete|undelete|merge)\b[^']*'", line, re.IGNORECASE):
                            findings.append(
                                Finding(rel, i + 1, "access-level",
                                        "DML statement without explicit AccessLevel.USER_MODE / SYSTEM_MODE")
                            )
    return findings


FUTURE_RE = re.compile(r"@\s*future\b", re.IGNORECASE)


def check_no_future(text: str, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines()):
        if FUTURE_RE.search(line):
            findings.append(
                Finding(rel, i + 1, "no-future",
                        "@future annotation forbidden — use queueables with System.Finalizer instead")
            )
    return findings


SEEALLDATA_RE = re.compile(r"@\s*IsTest\s*\([^)]*SeeAllData\s*=\s*true\b", re.IGNORECASE)


def check_no_seealldata(text: str, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines()):
        if SEEALLDATA_RE.search(line):
            findings.append(
                Finding(rel, i + 1, "no-seealldata",
                        "SeeAllData=true forbidden in tests — construct fixtures with @TestSetup")
            )
    return findings


FOR_LOOP_RE = re.compile(r"^\s*(?:for|while)\s*\(", re.MULTILINE)


def check_soql_dml_in_loop(text: str, rel: str) -> list[Finding]:
    """Flag SOQL [SELECT ...] or DML statement inside a for/while loop body.

    Heuristic: find each `for (...)` / `while (...)` opening; track brace
    depth; within the body, flag any SOQL_INLINE_RE / DML_STMT_RE match.
    """
    findings: list[Finding] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if FOR_LOOP_RE.match(line):
            # Find the opening brace (may be on this or next non-comment line)
            j = i
            while j < len(lines) and "{" not in lines[j]:
                j += 1
            if j >= len(lines):
                i += 1
                continue
            depth = lines[j].count("{") - lines[j].count("}")
            j += 1
            while j < len(lines) and depth > 0:
                body_line = lines[j]
                body_stripped = body_line.strip()
                if not (body_stripped.startswith("//") or body_stripped.startswith("*")):
                    if SOQL_INLINE_RE.search(body_line):
                        findings.append(
                            Finding(rel, j + 1, "soql-in-loop",
                                    "SOQL query inside loop body — bulkify")
                        )
                    if re.search(r"^\s*(?:insert|update|upsert|delete|undelete|merge|Database\.\w+\s*\()", body_line, re.IGNORECASE):
                        # Reject string literals containing the keyword
                        if not re.search(r'"[^"]*\b(insert|update|upsert|delete|undelete|merge)\b[^"]*"', body_line, re.IGNORECASE) \
                           and not re.search(r"'[^']*\b(insert|update|upsert|delete|undelete|merge)\b[^']*'", body_line, re.IGNORECASE):
                            findings.append(
                                Finding(rel, j + 1, "dml-in-loop",
                                        "DML statement inside loop body — bulkify into a single DML on a collection")
                            )
                depth += body_line.count("{") - body_line.count("}")
                j += 1
            i = j
        else:
            i += 1
    return findings


# 15- or 18-char Salesforce ID literal in source
HARDCODED_ID_RE = re.compile(r"['\"](001|003|005|006|00G|0WO|0F9|a[A-Za-z0-9]{2})[A-Za-z0-9]{12,15}['\"]")


def check_hardcoded_id(text: str, rel: str) -> list[Finding]:
    """Flag hardcoded Salesforce IDs in Apex source. Common prefixes only."""
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        if HARDCODED_ID_RE.search(line):
            findings.append(
                Finding(rel, i + 1, "hardcoded-id",
                        "hardcoded Salesforce ID literal — use Custom Metadata, Custom Setting, or query by Name/DeveloperName instead")
            )
    return findings


HARDCODED_URL_RE = re.compile(r"['\"]https?://[^'\"]*\.(?:salesforce|force|cloudforce|visualforce|salesforce-experience)\.com[^'\"]*['\"]")


def check_hardcoded_url(text: str, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        if HARDCODED_URL_RE.search(line):
            findings.append(
                Finding(rel, i + 1, "hardcoded-url",
                        "hardcoded Salesforce URL — use URL.getOrgDomainURL() or a Named Credential")
            )
    return findings


# ---------------------------------------------------------------------------
# Permission set checks
# ---------------------------------------------------------------------------

PERMSET_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]{2,7}_[A-Z][A-Za-z0-9]+_(?:Read|Write|Full|Execute|Admin)$")


def check_perm_set_naming(filename: str, rel: str) -> list[Finding]:
    """The permset file basename (without .permissionset-meta.xml) must match
    [AppPrefix]_[Component]_[AccessLevel]."""
    base = filename.replace(".permissionset-meta.xml", "")
    if PERMSET_NAME_RE.match(base):
        return []
    return [
        Finding(rel, 1, "perm-set-naming",
                f"permission set name '{base}' does not match [AppPrefix]_[Component]_[AccessLevel] "
                f"(AppPrefix 3-8 PascalCase, AccessLevel ∈ Read|Write|Full|Execute|Admin)")
    ]


VIEW_ALL_RE = re.compile(r"<name>\s*ViewAllData\s*</name>\s*<enabled>\s*true\s*</enabled>", re.IGNORECASE | re.DOTALL)
MODIFY_ALL_RE = re.compile(r"<name>\s*ModifyAllData\s*</name>\s*<enabled>\s*true\s*</enabled>", re.IGNORECASE | re.DOTALL)


def check_perm_set_anti_patterns(text: str, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    if VIEW_ALL_RE.search(text):
        # Find the line of the offending block
        line_no = 1
        for i, line in enumerate(text.splitlines()):
            if "ViewAllData" in line:
                line_no = i + 1
                break
        findings.append(
            Finding(rel, line_no, "perm-set-anti-pattern",
                    "ViewAllData granted in functional permission set — split sensitive data into a separate, restricted set")
        )
    if MODIFY_ALL_RE.search(text):
        line_no = 1
        for i, line in enumerate(text.splitlines()):
            if "ModifyAllData" in line:
                line_no = i + 1
                break
        findings.append(
            Finding(rel, line_no, "perm-set-anti-pattern",
                    "ModifyAllData granted in functional permission set — never grant in a feature set; reserve for system-level admin sets only")
        )
    return findings


# ---------------------------------------------------------------------------
# ApexDoc presence (heuristic)
# ---------------------------------------------------------------------------

PUBLIC_METHOD_RE = re.compile(
    r"^\s*(?:@[\w.]+(?:\([^)]*\))?\s*\n)*\s*(?:global|public)\s+(?:static\s+)?(?!class\b)(?!enum\b)(?!interface\b)\S+\s+\w+\s*\(",
    re.MULTILINE,
)


def check_apex_doc_present(text: str, rel: str) -> list[Finding]:
    """Heuristic check: a public class or method should have an immediately-
    preceding ApexDoc (`/** ... */`) block. Reports up to 1 finding per file
    (so the linter doesn't spam — quality-reviewer is the deeper agent).
    """
    findings: list[Finding] = []
    lines = text.splitlines()
    # Find the first public class or public method without preceding ApexDoc
    for i, line in enumerate(lines):
        if not re.match(r"^\s*(?:global|public)\s+(?:(?:static|virtual|abstract|with\s+sharing|without\s+sharing|inherited\s+sharing)\s+)*(?:class|interface|enum)\s+\w+", line) \
           and not re.match(r"^\s*(?:global|public)\s+(?:static\s+)?[\w<>,\s\[\]]+\s+\w+\s*\(", line):
            continue
        # Look back up to 5 lines for /** ... */
        has_doc = False
        for k in range(max(0, i - 5), i):
            if lines[k].strip().startswith("/**") or lines[k].strip().endswith("*/"):
                has_doc = True
                break
        if not has_doc:
            findings.append(
                Finding(rel, i + 1, "apex-doc",
                        "public class/method missing immediately-preceding ApexDoc /** ... */ block")
            )
            return findings  # one per file — the agent does deeper analysis
    return findings


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def lint_apex_file(path: Path, rel: str) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[Finding] = []
    out += check_sharing_keyword(text, rel)
    out += check_access_level(text, rel)
    out += check_no_future(text, rel)
    out += check_no_seealldata(text, rel)
    out += check_soql_dml_in_loop(text, rel)
    out += check_hardcoded_id(text, rel)
    out += check_hardcoded_url(text, rel)
    out += check_apex_doc_present(text, rel)
    return out


def lint_permset_file(path: Path, rel: str) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[Finding] = []
    out += check_perm_set_naming(path.name, rel)
    out += check_perm_set_anti_patterns(text, rel)
    return out


def run(root: Path) -> int:
    findings: list[Finding] = []

    for p in find_apex_files(root):
        rel = str(p.relative_to(root))
        findings.extend(lint_apex_file(p, rel))

    for p in find_permset_files(root):
        rel = str(p.relative_to(root))
        findings.extend(lint_permset_file(p, rel))

    for f in findings:
        print(f.format())

    return min(len(findings), 255)


def main() -> int:
    parser = argparse.ArgumentParser(description="sf-lint — Salesforce-rules static checker (subset)")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="Root directory to scan (default: cwd)")
    args = parser.parse_args()
    return run(args.root.resolve())


if __name__ == "__main__":
    sys.exit(main())
