#!/usr/bin/env bash
# Make a release package for relctl from a directory.
# Usage: tools/make-package.sh SOURCE_DIR PACKAGE
# SOURCE_DIR must contain the file VERSION. The script writes PACKAGE (a
# gzip-compressed tar file of the content of SOURCE_DIR) and PACKAGE.sha256.
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 SOURCE_DIR PACKAGE" >&2
    exit 2
fi
src=$1
pkg=$2

if [ ! -f "$src/VERSION" ]; then
    echo "$0: $src/VERSION is missing" >&2
    exit 1
fi

tar -czf "$pkg" -C "$src" .
sum=$(sha256sum <"$pkg")
printf '%s  %s\n' "${sum%% *}" "$(basename -- "$pkg")" >"$pkg.sha256"
echo "wrote $pkg and $pkg.sha256"
