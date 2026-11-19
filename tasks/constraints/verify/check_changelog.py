"""Check the CHANGELOG.md entry: check_changelog.py BASELINE_FILE NEW_FILE.

The new file must keep all non-empty lines of the baseline in order, and add
at least one bullet in the Unreleased section under a "### Fixed" or
"### Changed" heading. No bullet may be added in a released section.
"""

import re
import sys


def sections(lines):
    """Map each line index to (release heading, subsection heading)."""
    release = subsection = None
    result = []
    for line in lines:
        if line.startswith("## "):
            release, subsection = line.strip(), None
        elif line.startswith("### "):
            subsection = line[4:].strip()
        result.append((release, subsection))
    return result


def main(baseline_path, new_path):
    with open(baseline_path) as f:
        base = f.read().splitlines()
    with open(new_path) as f:
        new = f.read().splitlines()

    remaining = [line for line in base if line.strip()]
    added = []
    for i, line in enumerate(new):
        if remaining and line == remaining[0]:
            remaining.pop(0)
        elif line.strip():
            added.append(i)
    if remaining:
        print(f"baseline line removed or changed: {remaining[0]!r}")
        return 1

    where = sections(new)
    bullets = [i for i in added if new[i].lstrip().startswith(("- ", "* "))]
    if not bullets:
        print("no new entry")
        return 1
    ok = False
    for i in bullets:
        release, subsection = where[i]
        if release is None or not re.match(r"^## \[?Unreleased\]?\s*$", release, re.IGNORECASE):
            print(f"entry outside Unreleased: {new[i]!r} in {release!r}")
            return 1
        if subsection in ("Fixed", "Changed"):
            ok = True
    first_release = next((line for line in new if line.startswith("## ")), "")
    if not re.match(r"^## \[?Unreleased\]?\s*$", first_release, re.IGNORECASE):
        print("Unreleased is not the first section")
        return 1
    if not ok:
        print("new entry is not under '### Fixed' or '### Changed'")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
