#!/usr/bin/env bash
# CPAchecker witness-validation wrapper for tests/tester.py.
#
# Exits 0 only when the witness is confirmed, which is what the tester treats as
# a validated witness. A violation witness is confirmed when CPAchecker reports
# FALSE; a correctness witness is confirmed when it reports TRUE.
#
# Usage (via the tester):
#   --validator-command 'tests/validate_witness.sh {witness} {input} {property} {bits}'
#
# Set CPACHECKER_HOME to the CPAchecker installation directory.

set -uo pipefail

if [[ $# -lt 4 ]]; then
    echo "usage: $0 <witness> <input> <property> <bits>" >&2
    exit 2
fi

witness=$1
input=$2
property=$3
bits=$4

if [[ -z "${CPACHECKER_HOME:-}" ]]; then
    echo "CPACHECKER_HOME is not set; cannot validate witnesses" >&2
    exit 3
fi

cpa="$CPACHECKER_HOME/bin/cpachecker"
[[ -x "$cpa" ]] || cpa="$CPACHECKER_HOME/scripts/cpa.sh"
if [[ ! -x "$cpa" ]]; then
    echo "CPAchecker entrypoint not found under $CPACHECKER_HOME" >&2
    exit 3
fi

if [[ ! -s "$witness" ]]; then
    echo "witness is missing or empty: $witness" >&2
    exit 1
fi

# Violation witnesses carry an explicit violation flag; anything else is a correctness witness.
if grep -q 'key="violation"' "$witness"; then
    expected="Verification result: FALSE"
else
    expected="Verification result: TRUE"
fi

output=$("$cpa" \
    --witness-validation \
    --witness "$witness" \
    --spec "$property" \
    "-$bits" \
    "$input" 2>&1)

if grep -qF "$expected" <<<"$output"; then
    exit 0
fi

echo "$output" | tail -20 >&2
exit 1
