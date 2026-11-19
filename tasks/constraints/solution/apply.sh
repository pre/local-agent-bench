#!/usr/bin/env bash
# Commit the reference solution as one conventional commit.
set -euo pipefail
git -c safe.directory='*' add -A
git -c safe.directory='*' commit -q \
    -m "fix: Order pre-release tags by SemVer precedence" \
    -m "A release now sorts after its release candidates, and numeric
pre-release identifiers compare as numbers."
