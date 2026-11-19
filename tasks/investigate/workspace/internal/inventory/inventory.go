// Package inventory holds the nodes of a cluster and selects nodes by label.
package inventory

import (
	"sort"

	"example.com/rollout/internal/util"
)

// Inventory is the list of nodes of one cluster.
type Inventory struct {
	Cluster string `json:"cluster"`
	Nodes   []Node `json:"nodes"`
}

// Select returns the nodes that match sel, in inventory order.
func (inv *Inventory) Select(sel Selector) []Node {
	return util.Filter(inv.Nodes, sel.Matches)
}

// Lookup returns the node with the given name.
func (inv *Inventory) Lookup(name string) (Node, bool) {
	for _, n := range inv.Nodes {
		if n.Name == name {
			return n, true
		}
	}
	return Node{}, false
}

// Racks returns the names of all racks, sorted.
func (inv *Inventory) Racks() []string {
	racks := util.NewStringSet()
	for _, n := range inv.Nodes {
		racks.Add(n.Rack)
	}
	return racks.Sorted()
}

// SortByName sorts nodes by name.
func SortByName(nodes []Node) {
	sort.Slice(nodes, func(i, j int) bool { return nodes[i].Name < nodes[j].Name })
}

// SortByRack sorts nodes by rack and then by name.
func SortByRack(nodes []Node) {
	sort.Slice(nodes, func(i, j int) bool {
		if nodes[i].Rack != nodes[j].Rack {
			return nodes[i].Rack < nodes[j].Rack
		}
		return nodes[i].Name < nodes[j].Name
	})
}

// Names returns the names of nodes.
func Names(nodes []Node) []string {
	return util.Map(nodes, func(n Node) string { return n.Name })
}
