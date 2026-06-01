#!/bin/sh
# sf-lint wrapper — invoked by /architect, /proceed pre-merge gate, /sprint, or
# directly by a developer. Forwards to the Python implementation.
#
# Usage:
#   sh tools/sf-lint/check.sh                  # scan cwd
#   sh tools/sf-lint/check.sh --root <path>    # scan specific path
#
# Exit code: 0 on clean, otherwise min(num_findings, 255).
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/check.py" "$@"
