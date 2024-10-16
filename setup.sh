#!/usr/bin/env bash
# You only need to run this once.
# Download SVF binaries to svf directory.
# https://github.com/SVF-tools/SVF/releases/download/SVF-3.0/SVF-Ubuntu-22.04-x86.zip

binaries="https://github.com/SVF-tools/SVF/releases/download/SVF-3.0/SVF-Ubuntu-22.04-x86.zip"

echo "Downloading SVF"
curl -L "$binaries" -o "SVF.zip"

echo "Unzipping"
unzip -q "SVF.zip"

echo "Cleaning up"
rm -rf __MACOSX
rm -f "SVF.zip"
mv ./SVF-Ubuntu* ./svf

echo "Done"
