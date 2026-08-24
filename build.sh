#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dist="$root/dist"
package="$dist/svf-svc"
archive="$dist/svf-svc.zip"

runtime_files=(
    AbstractInterpretation.py
    cfl_reachability.py
    nondet.py
    svf_run.py
    util.py
    witness_output.py
    LICENSE.TXT
    requirements.txt
    smoketest.sh
)

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python_version="3.12"

rm -rf "$package" "$archive"
mkdir -p "$package"

python3 -m pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    --only-binary=:all: \
    --python-version "$python_version" \
    --target "$package" \
    -r "$root/requirements.txt"

for file in "${runtime_files[@]}"; do
    cp "$root/$file" "$package/$file"
done
chmod 755 "$package/svf_run.py"
chmod 755 "$package/smoketest.sh"

# Fix SABER's import
pysvf_root="$package/pysvf/SVF"
cp -f \
    "$pysvf_root/llvm-21.1.0.obj/lib/libLLVM.so" \
    "$pysvf_root/Release-build/lib/libLLVM.so.21.1"

# Memory analysis invokes these bundled executables and preloads bundled LLVM.
# Check that files are executable.
test -x "$package/pysvf/SVF/Release-build/bin/ae"
test -x "$package/pysvf/SVF/Release-build/bin/saber"

command -v zip >/dev/null || { echo "zip is required" >&2; exit 1; }
cd "$dist"
zip -r -9 "$archive" "$(basename "$package")"

printf 'Created %s\n' "$archive"
