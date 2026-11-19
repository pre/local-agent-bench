// Package health decides which nodes are healthy enough for an upgrade.
package health

import (
	"example.com/rollout/internal/inventory"
	"example.com/rollout/internal/util"
)

// Split returns the nodes that can be upgraded and the nodes that must be
// skipped. A node whose last health check failed is skipped: it needs a
// repair before an upgrade. A degraded node is upgraded.
func Split(nodes []inventory.Node) (ok, skipped []inventory.Node) {
	for _, n := range nodes {
		if n.Health == inventory.HealthFailed {
			skipped = append(skipped, n)
		}
	}
	ok = util.Filter(nodes, func(n inventory.Node) bool { return n.Health != inventory.HealthFailed })
	return ok, skipped
}
