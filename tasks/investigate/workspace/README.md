# rollout

`rollout` plans the batches of a rolling upgrade of cluster nodes. The
upgrade job drains and upgrades one batch at a time.

```
rollout plan  -inventory <file> [-policy <file>] [-o text|json]
rollout check -inventory <file> [-policy <file>]
rollout version
```

## Inventory

A JSON file with the nodes of one cluster. See `testdata/fleet-a.json`.
Each node has a name, a rack, labels and the result of its last health
check (`ok`, `degraded` or `failed`; the default is `ok`).

## Policy

A JSON file, see `testdata/policy-canary.json`:

| Key | Meaning |
|---|---|
| `selector` | Label selector of the nodes to upgrade. Empty selects all nodes |
| `exclude` | Label selector of nodes that are never upgraded. Default `role=control` |
| `canary.selector`, `canary.count` | Up to `count` nodes that match the selector (first by name) are upgraded first, in a batch of their own |
| `maxBatchSize` | Largest number of nodes in one batch. Default 4 |
| `maxUnavailablePerRack` | Largest number of nodes of one rack in one batch. Default 1 |

A selector is a comma-separated list of terms: `key=value`, `key!=value`,
`key` (the label exists) and `!key` (the label does not exist).

Nodes whose health check failed are not in the plan. The plan lists them
as skipped.

`rollout plan` checks each plan before it prints it: each node is in one
batch only, and no batch breaks the limits of the policy.
