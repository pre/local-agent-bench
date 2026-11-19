Clusters that run a release candidate never move to the final release. Example: `ingress-gw` runs `1.4.0-rc.2`, the registry has `1.4.0`, and `select_tag("1.4.0-rc.2", tags, track="patch")` returns `None`. The staging channel (`allow_prerelease=True`) has a similar problem: it stays on `2.0.0-rc.9` although `2.0.0-rc.10` is in the registry.

Please fix this in `imagepolicy`. The order of tags must follow the precedence rules of SemVer 2.0.0. Build metadata stays ignored, as it is now.

Constraints:
- Do not change `imagepolicy/api.py`. It is the public API that the rollout controller and two other teams import, and each change to it needs a separate review.
- Keep the names and signatures of all public functions in `imagepolicy/`.
- Add an entry for the fix to `CHANGELOG.md`, in the format that the file uses.
- Make exactly one git commit on top of the current `main` that contains all your changes. The commit title must be a conventional commit title of the form `fix: <Capitalized verb> ...`, with the verb in the present tense, at most 72 characters.
- When you are done, the working tree must be clean: no uncommitted changes and no untracked files.
