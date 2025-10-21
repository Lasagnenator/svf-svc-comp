#!/usr/bin/env bash
set -euo pipefail

# Test svf_run.py
run() {
    cfile="$1"
    propfile="$2"
    expect="$3"
    mode="$4"

    output=$(python3 "./svf_run.py" --prop "$propfile" "$cfile")

    if [[ "$mode" == "has" ]]; then
        if [[ "$output" != *"${expect}"* ]]; then
            echo "${cfile}: expected '${expect}' but not found"
            exit 1
        fi
    elif [[ "$mode" == "not" ]]; then
        if [[ "$output" == *"${expect}"* ]]; then
            echo "${cfile}: unexpected '${expect}'"
            exit 1
        fi
    fi
}

# Expect reach to be correct
run "./tests/basic_reach.c" "./tests/unreach-call.prp" "REACH Incorrect" not

# Expect overflow to be detected and print "OVERFLOW Incorrect"
run "./tests/basic_mem_overflow.c" "./tests/no-overflow.prp" "OVERFLOW Incorrect" has