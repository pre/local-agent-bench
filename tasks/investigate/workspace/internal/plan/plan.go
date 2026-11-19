// Package plan computes the batches of a rolling upgrade.
package plan

import (
	"example.com/rollout/internal/health"
	"example.com/rollout/internal/inventory"
	"example.com/rollout/internal/policy"
	"example.com/rollout/internal/util"
)

// Batch is a group of nodes that are drained and upgraded at the same time.
type Batch struct {
	Canary bool
	Nodes  []inventory.Node
}

// Plan is the ordered list of batches for one cluster.
type Plan struct {
	Cluster string
	Batches []Batch
	// Skipped holds the names of the selected nodes that are not in the
	// plan because their health check failed.
	Skipped []string
}

// Build computes the plan for the nodes of inv that pol selects.
//
// The canary batch (if the policy has one) comes first. The other nodes
// follow in batches, see makeBatches.
func Build(inv *inventory.Inventory, pol *policy.Policy) (*Plan, error) {
	sel, err := pol.Parse()
	if err != nil {
		return nil, err
	}

	selected := inv.Select(sel.Select)
	if !sel.Exclude.Empty() {
		selected = util.Filter(selected, func(n inventory.Node) bool { return !sel.Exclude.Matches(n) })
	}
	eligible, skipped := health.Split(selected)

	p := &Plan{Cluster: inv.Cluster, Skipped: inventory.Names(skipped)}

	canaries := pickCanaries(inv, eligible, sel.Canary, pol.Canary.Count)
	if len(canaries) > 0 {
		p.Batches = append(p.Batches, Batch{Canary: true, Nodes: canaries})
	}

	isCanary := util.NewStringSet(inventory.Names(canaries)...)
	rest := util.Filter(eligible, func(n inventory.Node) bool { return !isCanary.Has(n.Name) })
	for _, nodes := range makeBatches(rest, pol.MaxBatchSize, pol.MaxUnavailablePerRack) {
		p.Batches = append(p.Batches, Batch{Nodes: nodes})
	}
	return p, nil
}

// NodeCount returns the number of nodes in all batches.
func (p *Plan) NodeCount() int {
	n := 0
	for _, b := range p.Batches {
		n += len(b.Nodes)
	}
	return n
}
