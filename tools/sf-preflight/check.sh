#!/bin/sh
# sf-preflight wrapper — invoked by /architect, /canary Step 2, /proceed
# Phase 4.5, or directly by a developer. Forwards to the perm-set Node check.
#
# Usage:
#   sh tools/sf-preflight/check.sh permsets --workspace force-app --target-org <alias>
#   sh tools/sf-preflight/check.sh permsets --offline --workspace force-app
#
# The first arg selects the check (currently only `permsets`; REQ-F adds more).
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CHECK="$1"
shift 2>/dev/null || true
case "$CHECK" in
  permsets) exec node "$SCRIPT_DIR/check-permsets.mjs" "$@" ;;
  metadata) exec node "$SCRIPT_DIR/check-metadata.mjs" "$@" ;;
  -h|--help|"")
    cat <<EOF
Usage: $0 <check> [options]
  permsets   FLS / required-field / formula / master-detail validation (REQ-B)
  metadata   Cross-reference / object / layout / record-type validation (REQ-F)
EOF
    exit 0
    ;;
  *)
    echo "ERROR: unknown check '$CHECK'. Run with --help for the list." >&2
    exit 2
    ;;
esac
