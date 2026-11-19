package cli

import (
	"flag"
	"fmt"
	"log"

	"example.com/rollout/internal/inventory"
	"example.com/rollout/internal/policy"
)

// inputFlags are the flags that plan and check have in common.
type inputFlags struct {
	inventory string
	policy    string
}

func (f *inputFlags) register(fs *flag.FlagSet) {
	fs.StringVar(&f.inventory, "inventory", "", "inventory `file` (JSON, necessary)")
	fs.StringVar(&f.policy, "policy", "", "policy `file` (JSON, default: the built-in policy)")
}

func (f *inputFlags) load(logger *log.Logger) (*inventory.Inventory, *policy.Policy, error) {
	if f.inventory == "" {
		return nil, nil, fmt.Errorf("-inventory is necessary")
	}
	inv, err := inventory.Load(f.inventory)
	if err != nil {
		return nil, nil, err
	}
	logger.Printf("loaded %d nodes of cluster %s from %s", len(inv.Nodes), inv.Cluster, f.inventory)

	pol := policy.Default
	if f.policy != "" {
		p, err := policy.Load(f.policy)
		if err != nil {
			return nil, nil, err
		}
		pol = *p
	}
	return inv, &pol, nil
}
