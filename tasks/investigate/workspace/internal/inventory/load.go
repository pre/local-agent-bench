package inventory

import (
	"encoding/json"
	"fmt"
	"os"
)

// Load reads an inventory from a JSON file and checks it.
func Load(path string) (*Inventory, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var inv Inventory
	if err := json.Unmarshal(data, &inv); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if err := inv.Check(); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return &inv, nil
}

// Check returns an error if a node has no name or no rack, if two nodes
// have the same name, or if a health value is unknown. A missing health
// value is set to "ok".
func (inv *Inventory) Check() error {
	seen := make(map[string]bool, len(inv.Nodes))
	for i := range inv.Nodes {
		n := &inv.Nodes[i]
		switch {
		case n.Name == "":
			return fmt.Errorf("node %d: missing name", i+1)
		case n.Rack == "":
			return fmt.Errorf("node %s: missing rack", n.Name)
		case seen[n.Name]:
			return fmt.Errorf("node %s: duplicate name", n.Name)
		}
		seen[n.Name] = true
		switch n.Health {
		case "":
			n.Health = HealthOK
		case HealthOK, HealthDegraded, HealthFailed:
		default:
			return fmt.Errorf("node %s: unknown health %q", n.Name, n.Health)
		}
	}
	return nil
}
