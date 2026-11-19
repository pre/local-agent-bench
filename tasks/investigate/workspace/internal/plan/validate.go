package plan

import (
	"fmt"

	"example.com/rollout/internal/policy"
)

// Validate checks the plan against the policy: each node is in one batch
// only, no batch is larger than allowed, no batch has too many nodes of
// one rack, and only the first batch is a canary batch.
func Validate(p *Plan, pol *policy.Policy) error {
	batchOf := make(map[string]int)
	for i, b := range p.Batches {
		num := i + 1
		if len(b.Nodes) == 0 {
			return fmt.Errorf("batch %d is empty", num)
		}
		if b.Canary && i != 0 {
			return fmt.Errorf("batch %d: only the first batch can be a canary batch", num)
		}
		limit := pol.MaxBatchSize
		if b.Canary {
			limit = pol.Canary.Count
		}
		if len(b.Nodes) > limit {
			return fmt.Errorf("batch %d: %d nodes, the limit is %d", num, len(b.Nodes), limit)
		}
		perRack := make(map[string]int)
		for _, n := range b.Nodes {
			if prev, ok := batchOf[n.Name]; ok {
				return fmt.Errorf("batch %d: node %q is already in batch %d", num, n.Name, prev)
			}
			batchOf[n.Name] = num
			perRack[n.Rack]++
			if !b.Canary && perRack[n.Rack] > pol.MaxUnavailablePerRack {
				return fmt.Errorf("batch %d: more than %d nodes of rack %s", num, pol.MaxUnavailablePerRack, n.Rack)
			}
		}
	}
	return nil
}
