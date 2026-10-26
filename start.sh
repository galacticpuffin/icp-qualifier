#!/bin/sh
# One-command local start: no dependencies beyond Python 3.11+.
cd "$(dirname "$0")" && exec python3 -m icpq serve "$@"
