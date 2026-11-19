`rollout plan` fails for the build-b cluster since we added a canary batch to its policy:

```
$ go run ./cmd/rollout plan -inventory testdata/fleet-b.json -policy testdata/policy-canary.json
rollout: load.go:31: loaded 18 nodes of cluster build-b from testdata/fleet-b.json
rollout: plan.go:35: 12 nodes in 5 batches, 1 skipped
rollout: plan.go:37: plan is not valid: batch 3: node "gpu-b07" is already in batch 1
exit status 1
```

The same inventory with `testdata/policy-gpu.json` (no canaries) gives a plan without errors, and `go test ./...` passes.

Please find the root cause and fix it. The plan must contain each selected healthy node exactly once, with the canaries in the first batch. The validation is correct, so do not weaken it, and do not change the output format.
