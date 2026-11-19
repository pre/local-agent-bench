package plan

import (
	"example.com/rollout/internal/inventory"
	"example.com/rollout/internal/util"
)

// pickCanaries returns up to count canary nodes: the eligible nodes that
// match the canary selector, first by name.
func pickCanaries(inv *inventory.Inventory, eligible []inventory.Node, canarySel inventory.Selector, count int) []inventory.Node {
	if count == 0 {
		return nil
	}
	candidates := inv.Select(canarySel)
	isEligible := util.NewStringSet(inventory.Names(eligible)...)
	candidates = util.Filter(candidates, func(n inventory.Node) bool { return isEligible.Has(n.Name) })
	inventory.SortByName(candidates)
	if len(candidates) > count {
		candidates = candidates[:count]
	}
	return candidates
}
