package plan

import (
	"encoding/json"
	"fmt"
	"io"
	"strings"

	"example.com/rollout/internal/inventory"
)

// WriteText writes the plan as text, one line per batch.
func WriteText(w io.Writer, p *Plan) error {
	fmt.Fprintf(w, "cluster %s: %d nodes in %d batches\n", p.Cluster, p.NodeCount(), len(p.Batches))
	for i, b := range p.Batches {
		kind := ""
		if b.Canary {
			kind = " (canary)"
		}
		fmt.Fprintf(w, "batch %d%s: %s\n", i+1, kind, strings.Join(inventory.Names(b.Nodes), " "))
	}
	if len(p.Skipped) > 0 {
		fmt.Fprintf(w, "skipped (health check failed): %s\n", strings.Join(p.Skipped, " "))
	}
	return nil
}

type jsonBatch struct {
	Canary bool     `json:"canary"`
	Nodes  []string `json:"nodes"`
}

type jsonPlan struct {
	Cluster string      `json:"cluster"`
	Batches []jsonBatch `json:"batches"`
	Skipped []string    `json:"skipped"`
}

// WriteJSON writes the plan as JSON.
func WriteJSON(w io.Writer, p *Plan) error {
	out := jsonPlan{Cluster: p.Cluster, Batches: []jsonBatch{}, Skipped: []string{}}
	for _, b := range p.Batches {
		out.Batches = append(out.Batches, jsonBatch{Canary: b.Canary, Nodes: inventory.Names(b.Nodes)})
	}
	out.Skipped = append(out.Skipped, p.Skipped...)
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	return enc.Encode(out)
}
