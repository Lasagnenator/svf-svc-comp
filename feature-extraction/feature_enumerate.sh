#!/bin/sh

features="$(for path in ../sv-benchmarks/c/*; do
    if [ "$path" = "feature_enumerate.sh" ]; then
        continue
    fi
    if [ -f "$path" ]; then
        grep -E 'extern [^(]+' "$path" | sed -E 's/\(.*//g'
    else
        for file in "$path"/*; do
            if [ -f "$file" ]; then
                grep -E 'extern [^(]+' "$file" | sed -E 's/\(.*//g'
            fi
        done
    fi
done)"

echo "$features" | sort | uniq | grep -E 'VERIFIER' | sed -E 's/ +/ /g' > verifier_enumeration.txt
