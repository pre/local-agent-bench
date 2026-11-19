# imagepolicy

Selects the container image tag that the rollout controller deploys to a
cluster, from the tags in the registry and the update track of the cluster.

```python
from imagepolicy.api import select_tag

select_tag("1.9.0", ["1.9.3", "1.10.2", "2.0.0", "latest"], track="minor")  # "1.10.2"
```

Tracks: `patch` (same minor version), `minor` (same major version), `major`
(any newer version). Pre-release tags are only selected with
`allow_prerelease=True`.

`imagepolicy/api.py` is the public API. Other teams import it, so changes to
it need a review by the owners of the rollout controller.

## Tests

```
python -m unittest discover -s tests -t .
```

## Commits

Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`). Each change adds
an entry to `CHANGELOG.md` under `Unreleased`.
