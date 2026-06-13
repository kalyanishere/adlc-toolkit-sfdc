#!/usr/bin/env python3
"""
Source-only audit CLI for the ADLC pipeline.

Wraps the v1.2.13 Apex pattern matcher and LWC analyzer to run against a local
working tree (force-app/, package.json, etc.) without needing a Salesforce org.

Designed to be called from /reflect (Phase 5a) before /canary deploys. Emits
machine-readable JSON for the gate AND a human-readable Markdown summary for
the developer. Exits non-zero when any severity in --fail-on has count > 0.

Usage examples
--------------
  # Audit the entire force-app/ tree, fail on CRITICAL or HIGH:
  python3 audit_source.py --root . --fail-on CRITICAL,HIGH \\
      --json-out .adlc/runtime/audit/source-audit.json \\
      --md-out  .adlc/runtime/audit/source-audit.md

  # Audit only the changed files in this branch (diff scope) -- much faster:
  python3 audit_source.py --root . --files-from .adlc/runtime/audit/diff-files.txt \\
      --fail-on CRITICAL,HIGH

  # Strict gate: any severity at all fails the build.
  python3 audit_source.py --fail-on CRITICAL,HIGH,MEDIUM,LOW

Exit codes
----------
  0  success, gate passed
  1  gate failed (one or more --fail-on severities had findings)
  2  usage / I/O error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# The vendored modules live next to this script.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# These imports reach into the vendored v1.2.13 codebase. Both modules are
# stdlib-only (re, typing, dataclasses, enum) so importing them is cheap and
# does not pull pandas/openpyxl/simple-salesforce.
from pattern_matcher import analyze_apex_code  # noqa: E402
from lwc_analyzer import analyze_lwc_component  # noqa: E402

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
DEFAULT_SKIP_DIRS = {
    "node_modules", ".git", ".sfdx", ".sf", ".vscode", ".idea",
    "audit-results", "audit_reports", ".worktrees", ".adlc",
}


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _is_under(path: Path, ancestors: Iterable[Path]) -> bool:
    p = path.resolve()
    return any(p == a or a in p.parents for a in ancestors)


def _walk_force_app(root: Path, skip_paths: Sequence[str]) -> Tuple[List[Path], List[Path], List[Path]]:
    """Walk force-app/ (or any sfdx package_directory under root) and return
    the set of (apex files, trigger files, lwc bundle dirs)."""
    apex: List[Path] = []
    triggers: List[Path] = []
    lwc_bundles: List[Path] = []

    pkg_dirs: List[Path] = []
    sfdx_proj = root / "sfdx-project.json"
    if sfdx_proj.exists():
        try:
            data = json.loads(sfdx_proj.read_text())
            for pd in data.get("packageDirectories", []) or []:
                p = pd.get("path")
                if p:
                    pkg_dirs.append((root / p).resolve())
        except Exception:
            pass
    if not pkg_dirs:
        # Fallback: assume force-app/ if it exists.
        fa = root / "force-app"
        if fa.exists():
            pkg_dirs.append(fa.resolve())

    skip_resolved = {(root / s).resolve() for s in skip_paths}
    skip_names = set(DEFAULT_SKIP_DIRS)

    for pkg_dir in pkg_dirs:
        if not pkg_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(pkg_dir):
            # Prune skip directories in-place.
            dirnames[:] = [d for d in dirnames if d not in skip_names]
            here = Path(dirpath).resolve()
            if _is_under(here, skip_resolved):
                dirnames[:] = []
                continue

            # LWC bundle: dir under .../lwc/<bundle> with same-named .js + .html
            if here.parent.name == "lwc":
                bundle_name = here.name
                if (here / f"{bundle_name}.js").exists():
                    lwc_bundles.append(here)
                # Don't descend into __tests__ etc; analyzer reads the two files directly.
                dirnames[:] = []
                continue

            for fn in filenames:
                fpath = here / fn
                if fn.endswith(".cls"):
                    apex.append(fpath)
                elif fn.endswith(".trigger"):
                    triggers.append(fpath)

    return apex, triggers, lwc_bundles


def _filter_to_files_from(
    apex: List[Path],
    triggers: List[Path],
    lwc_bundles: List[Path],
    files_from: Path,
) -> Tuple[List[Path], List[Path], List[Path]]:
    """Restrict scan to a list of changed files (one per line, repo-relative
    or absolute)."""
    try:
        wanted = {
            Path(line.strip()).resolve()
            for line in files_from.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
    except FileNotFoundError:
        print(f"audit_source: --files-from path not found: {files_from}", file=sys.stderr)
        sys.exit(2)

    apex_f = [p for p in apex if p.resolve() in wanted]
    trig_f = [p for p in triggers if p.resolve() in wanted]
    lwc_f = []
    for bundle in lwc_bundles:
        # Bundle hits if any wanted path is inside it.
        if any(w == bundle or bundle in w.parents for w in wanted):
            lwc_f.append(bundle)
    return apex_f, trig_f, lwc_f


# ---------------------------------------------------------------------------
# Findings normalization
# ---------------------------------------------------------------------------

def _normalize_severity(value: Any) -> str:
    if value is None:
        return "MEDIUM"
    s = str(value).strip().upper()
    return s if s in SEVERITIES else "MEDIUM"


def _violation_to_dict(v: Any, file_rel: str) -> Dict[str, Any]:
    """Convert a pattern_matcher.Violation dataclass into a plain dict."""
    if is_dataclass(v):
        d = asdict(v)
    else:
        d = dict(v)
    vtype = d.get("violation_type")
    # Enum -> .value
    if hasattr(vtype, "value"):
        vtype = vtype.value
    return {
        "kind": "apex",
        "file": file_rel,
        "line": d.get("line_number"),
        "severity": _normalize_severity(d.get("criticality")),
        "rule": str(vtype) if vtype is not None else "Unknown",
        "snippet": (d.get("code_snippet") or "").strip()[:200],
        "recommendation": d.get("recommendation") or "",
        "is_direct": d.get("is_direct", True),
        "call_chain": d.get("call_chain"),
    }


def _lwc_issue_to_dict(issue: Dict[str, Any], file_rel: str) -> Dict[str, Any]:
    return {
        "kind": "lwc",
        "file": file_rel,
        "line": issue.get("line_number"),
        "severity": _normalize_severity(issue.get("criticality")),
        "rule": issue.get("rule_name") or issue.get("category") or "LWC",
        "snippet": (issue.get("snippet") or "").strip()[:200],
        "recommendation": issue.get("recommendation") or "",
        "category": issue.get("category"),
    }


# ---------------------------------------------------------------------------
# Analyzer drivers
# ---------------------------------------------------------------------------

def _scan_apex(files: List[Path], root: Path, *, is_trigger: bool) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in files:
        try:
            code = f.read_text(errors="replace")
        except Exception as exc:
            print(f"audit_source: skip {f} ({exc})", file=sys.stderr)
            continue
        rel = str(f.relative_to(root)) if f.is_absolute() else str(f)
        for v in analyze_apex_code(f.name, code, is_trigger=is_trigger):
            out.append(_violation_to_dict(v, rel))
    return out


def _scan_lwc(bundles: List[Path], root: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for bundle in bundles:
        name = bundle.name
        js = bundle / f"{name}.js"
        html = bundle / f"{name}.html"
        js_code = js.read_text(errors="replace") if js.exists() else ""
        html_code = html.read_text(errors="replace") if html.exists() else ""
        rel = str(bundle.relative_to(root)) if bundle.is_absolute() else str(bundle)
        for issue in analyze_lwc_component(name, js_code, html_code):
            file_rel = f"{rel}/{issue.get('file_name', name)}"
            out.append(_lwc_issue_to_dict(issue, file_rel))
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _summarize(findings: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = Counter(f["severity"] for f in findings)
    summary = {sev: counts.get(sev, 0) for sev in SEVERITIES}
    summary["TOTAL"] = sum(summary[s] for s in SEVERITIES)
    return summary


def _markdown_report(findings: List[Dict[str, Any]], summary: Dict[str, int],
                     started: datetime, root: Path, scope: str) -> str:
    lines: List[str] = []
    lines.append(f"# Source Audit Report — {started.isoformat()}")
    lines.append("")
    lines.append(f"- **Root:** `{root}`")
    lines.append(f"- **Scope:** {scope}")
    lines.append(f"- **Tool version:** {(SCRIPT_DIR / 'tool_version.json').read_text().strip() if (SCRIPT_DIR / 'tool_version.json').exists() else 'unknown'}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---|")
    for sev in SEVERITIES:
        lines.append(f"| {sev} | {summary.get(sev, 0)} |")
    lines.append(f"| **Total** | **{summary.get('TOTAL', 0)}** |")
    lines.append("")

    for sev in SEVERITIES:
        bucket = [f for f in findings if f["severity"] == sev]
        if not bucket:
            continue
        lines.append(f"## {sev} ({len(bucket)})")
        lines.append("")
        for f in bucket:
            line_str = f":{f['line']}" if f.get("line") else ""
            lines.append(f"- **{f['rule']}** — `{f['file']}{line_str}`")
            if f.get("snippet"):
                lines.append(f"  - `{f['snippet']}`")
            if f.get("recommendation"):
                lines.append(f"  - _Fix:_ {f['recommendation']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Source-only Salesforce code audit (Apex + LWC) for ADLC pipelines.",
    )
    parser.add_argument("--root", default=".", help="Project root (default: cwd)")
    parser.add_argument(
        "--files-from",
        help="Path to a file with one source path per line; restricts the scan to those files only "
             "(use git diff --name-only to populate).",
    )
    parser.add_argument(
        "--fail-on",
        default="CRITICAL,HIGH",
        help="Comma-separated severities that cause non-zero exit when count > 0 "
             "(default: CRITICAL,HIGH). Use 'NONE' to disable gating.",
    )
    parser.add_argument(
        "--json-out",
        help="Write machine-readable JSON report to this path.",
    )
    parser.add_argument(
        "--md-out",
        help="Write human-readable Markdown report to this path.",
    )
    parser.add_argument(
        "--skip-paths",
        default="",
        help="Comma-separated repo-relative paths to skip in addition to defaults "
             "(node_modules, .git, .sfdx, .adlc, etc.).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout summary (still writes --json-out / --md-out).",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print audit tool version and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.version:
        ver_path = SCRIPT_DIR / "tool_version.json"
        try:
            v = json.loads(ver_path.read_text()).get("version", "unknown")
        except Exception:
            v = "unknown"
        print(f"sf-code-audit (source mode) v{v}")
        return 0

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"audit_source: --root not found: {root}", file=sys.stderr)
        return 2

    skip_paths = [s.strip() for s in args.skip_paths.split(",") if s.strip()]
    apex, triggers, lwc_bundles = _walk_force_app(root, skip_paths)

    scope_label = "full force-app/"
    if args.files_from:
        ff = Path(args.files_from)
        apex, triggers, lwc_bundles = _filter_to_files_from(apex, triggers, lwc_bundles, ff)
        scope_label = f"diff scope ({ff})"

    findings: List[Dict[str, Any]] = []
    findings.extend(_scan_apex(apex, root, is_trigger=False))
    findings.extend(_scan_apex(triggers, root, is_trigger=True))
    findings.extend(_scan_lwc(lwc_bundles, root))

    summary = _summarize(findings)
    started = datetime.now(timezone.utc)

    payload = {
        "tool": "sf-code-audit-source",
        "version": (SCRIPT_DIR / "tool_version.json").read_text().strip()
        if (SCRIPT_DIR / "tool_version.json").exists() else None,
        "started_at": started.isoformat(),
        "root": str(root),
        "scope": scope_label,
        "files_scanned": {
            "apex": len(apex),
            "triggers": len(triggers),
            "lwc_bundles": len(lwc_bundles),
        },
        "summary": summary,
        "findings": findings,
    }

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2))

    if args.md_out:
        out = Path(args.md_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_markdown_report(findings, summary, started, root, scope_label))

    fail_on_raw = (args.fail_on or "").strip().upper()
    fail_on: List[str] = []
    if fail_on_raw and fail_on_raw != "NONE":
        fail_on = [s.strip() for s in fail_on_raw.split(",") if s.strip() in SEVERITIES]

    gate_failed = any(summary.get(sev, 0) > 0 for sev in fail_on)

    if not args.quiet:
        print(f"sf-code-audit: scanned {len(apex)} apex, {len(triggers)} triggers, "
              f"{len(lwc_bundles)} LWC bundles")
        for sev in SEVERITIES:
            if summary.get(sev, 0):
                print(f"  {sev:8s} {summary[sev]}")
        if gate_failed:
            print(f"GATE FAILED: one or more of {fail_on} had findings.")
        else:
            print("GATE OK")

    return 1 if gate_failed else 0


if __name__ == "__main__":
    sys.exit(main())
