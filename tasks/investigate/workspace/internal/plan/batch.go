package plan

import "example.com/rollout/internal/inventory"

// makeBatches puts nodes into batches of at most maxSize nodes, with at
// most perRack nodes of the same rack in one batch.
//
// The nodes of each rack are taken in name order. A batch is filled by
// going over the racks in name order and taking up to perRack nodes from
// each, until the batch is full or all racks are visited.
func makeBatches(nodes []inventory.Node, maxSize, perRack int) [][]inventory.Node {
	sorted := append([]inventory.Node(nil), nodes...)
	inventory.SortByRack(sorted)

	var racks []string
	queues := make(map[string][]inventory.Node)
	for _, n := range sorted {
		if _, ok := queues[n.Rack]; !ok {
			racks = append(racks, n.Rack)
		}
		queues[n.Rack] = append(queues[n.Rack], n)
	}

	var batches [][]inventory.Node
	remaining := len(sorted)
	for remaining > 0 {
		var batch []inventory.Node
		for _, rack := range racks {
			take := min(perRack, len(queues[rack]), maxSize-len(batch))
			batch = append(batch, queues[rack][:take]...)
			queues[rack] = queues[rack][take:]
			remaining -= take
		}
		batches = append(batches, batch)
	}
	return batches
}
