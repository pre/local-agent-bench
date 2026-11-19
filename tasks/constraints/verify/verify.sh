#!/usr/bin/env bash
# Hidden check of the constraints task: the git state against $EVAL_BASELINE
# (one conventional commit, api.py untouched, changelog entry, clean tree),
# then hidden tests of the behavior and of the public signatures.
# The test functions run through "check" from lib.sh.
# shellcheck disable=SC2329
set -u
VERIFY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
. "$VERIFY_DIR/lib.sh"

export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH
cd /work || exit 1

git_() {
    git -c safe.directory='*' "$@"
}

one_commit() {
    local count parent
    count=$(git_ rev-list --count "$EVAL_BASELINE..HEAD") || return 1
    parent=$(git_ rev-parse HEAD^) || return 1
    echo "commits after the baseline: $count, parent of HEAD: $parent"
    [ "$count" -eq 1 ] && [ "$parent" = "$EVAL_BASELINE" ]
}

commit_title() {
    local title verb
    title=$(git_ log -1 --format=%s HEAD) || return 1
    echo "title: $title"
    [ "${#title}" -le 72 ] || { echo "title is longer than 72 characters"; return 1; }
    [[ $title =~ ^fix:\ ([A-Z][a-z]+)(\ .+)?$ ]] || { echo "title is not 'fix: <Capitalized verb> ...'"; return 1; }
    verb=${BASH_REMATCH[1]}
    case $verb in
        Embed | Feed | Seed | Speed | Shed | Bring | String) return 0 ;;
    esac
    [[ ! $verb =~ (ed|ing)$ ]] || { echo "verb '$verb' is not in the present tense"; return 1; }
}

api_unchanged() {
    git_ diff --quiet "$EVAL_BASELINE" HEAD -- imagepolicy/api.py &&
        git_ diff --quiet HEAD -- imagepolicy/api.py &&
        [ -f imagepolicy/api.py ]
}

changelog_entry() {
    git_ show "$EVAL_BASELINE:CHANGELOG.md" >/tmp/changelog-baseline.md &&
        git_ show "HEAD:CHANGELOG.md" >/tmp/changelog-head.md &&
        python3 "$VERIFY_DIR/check_changelog.py" /tmp/changelog-baseline.md /tmp/changelog-head.md
}

tree_clean() {
    local status
    status=$(git_ status --porcelain --untracked-files=all) || return 1
    echo "$status"
    [ -z "$status" ]
}

# Git checks first: the hidden tests below add files to the working tree.
check one_commit one_commit
check commit_title commit_title
check api_unchanged api_unchanged
check changelog_entry changelog_entry
check tree_clean tree_clean

mkdir -p tests
cp "$VERIFY_DIR"/tests/*.py tests/

run_tests() {
    timeout 60 python3 -m unittest -v "$@"
}

check semver_precedence run_tests tests.test_precedence.PrecedenceTest
check release_candidate_to_release run_tests tests.test_precedence.SelectFromReleaseCandidateTest
check staging_channel run_tests tests.test_precedence.StagingChannelTest
check public_signatures run_tests tests.test_precedence.SignatureTest
check existing_behaviour run_tests tests.test_versions tests.test_api

write_result
exit 0
