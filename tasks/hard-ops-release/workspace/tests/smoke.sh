#!/usr/bin/env bash
# Smoke test of relctl: install two releases in a scratch directory.
# Usage: tests/smoke.sh
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT

mkdir -p "$scratch/src" "$scratch/base"
printf 'base_dir=%s\nkeep=3\n' "$scratch/base" >"$scratch/relctl.conf"

for version in 1.0.0 1.1.0; do
    rm -rf "$scratch/src"
    mkdir -p "$scratch/src/bin"
    echo "$version" >"$scratch/src/VERSION"
    printf '#!/bin/sh\necho %s\n' "$version" >"$scratch/src/bin/app"
    chmod +x "$scratch/src/bin/app"
    "$root/tools/make-package.sh" "$scratch/src" "$scratch/app-$version.tar.gz" >/dev/null
    "$root/bin/relctl" --config "$scratch/relctl.conf" install "$scratch/app-$version.tar.gz"
done

[ "$(readlink "$scratch/base/current")" = "releases/1.1.0" ]
[ "$("$scratch/base/current/bin/app")" = "1.1.0" ]
echo "smoke test passed"
