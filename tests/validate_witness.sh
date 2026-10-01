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
# Set CPACHECKER_HOME to the CPAchecker installation directory. Verified against
# CPAchecker 4.2, which selects validation via config files rather than a flag.

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

kind=$(python3 - "$witness" <<'PY'
import sys
import yaml

with open(sys.argv[1]) as stream:
    types = {entry['entry_type'] for entry in yaml.safe_load(stream)}
if not types or not types <= {'violation_sequence', 'invariant_set'}:
    raise ValueError('unsupported YAML witness type')
print('violation' if 'violation_sequence' in types else 'correctness')
PY
) || exit 1

if [[ "$kind" == violation ]]; then
    config="$CPACHECKER_HOME/config/violation-witness-validation.properties"
    expected="Verification result: FALSE"
    timelimit=${VALIDATOR_TIMELIMIT:-90s}
else
    config="$CPACHECKER_HOME/config/correctness-witness-validation.properties"
    expected="Verification result: TRUE"
    timelimit=${VALIDATOR_TIMELIMIT:-300s}
fi

output_dir=$(mktemp -d) || exit 3
trap 'rm -rf -- "$output_dir"' EXIT

output=$("$cpa" \
    --config "$config" \
    --witness "$witness" \
    --spec "$property" \
    "--$bits" \
    --timelimit "$timelimit" \
    --no-output-files \
    --output-path "$output_dir" \
    "$input" 2>&1)
status=$?

if [[ $status -eq 0 ]] && grep -qF "$expected" <<<"$output"; then
    echo "$output"
    exit 0
fi

echo "$output" | tail -20 >&2
exit 1
