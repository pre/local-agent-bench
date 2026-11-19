// Package output writes nodes as a text table or as JSON.
package output

import (
	"encoding/json"
	"fmt"
	"io"
	"text/tabwriter"

	"example.com/nodeinv/internal/inventory"
)

// Format is an output format.
type Format string

const (
	Table Format = "table"
	JSON  Format = "json"
)

// ParseFormat returns the Format for s.
func ParseFormat(s string) (Format, error) {
	switch f := Format(s); f {
	case Table, JSON:
		return f, nil
	}
	return "", fmt.Errorf("unknown output format %q (want table or json)", s)
}

// WriteNodes writes nodes in the format f.
func WriteNodes(w io.Writer, f Format, nodes []inventory.Node) error {
	if f == JSON {
		return writeNodesJSON(w, nodes)
	}
	return writeNodesTable(w, nodes)
}

func writeNodesTable(w io.Writer, nodes []inventory.Node) error {
	tw := newTabWriter(w)
	fmt.Fprintln(tw, "NAME\tRACK\tSTATE\tGPUS\tUSED\tMODEL")
	for _, n := range nodes {
		model := n.Model
		if model == "" {
			model = "-"
		}
		fmt.Fprintf(tw, "%s\t%s\t%s\t%d\t%d\t%s\n", n.Name, n.Rack, n.State, n.GPUs, n.GPUsUsed, model)
	}
	return tw.Flush()
}

type jsonNode struct {
	Name     string `json:"name"`
	Rack     string `json:"rack"`
	State    string `json:"state"`
	GPUs     int    `json:"gpus"`
	GPUsUsed int    `json:"used"`
	Model    string `json:"model,omitempty"`
}

func writeNodesJSON(w io.Writer, nodes []inventory.Node) error {
	out := make([]jsonNode, 0, len(nodes))
	for _, n := range nodes {
		out = append(out, jsonNode{
			Name:     n.Name,
			Rack:     n.Rack,
			State:    string(n.State),
			GPUs:     n.GPUs,
			GPUsUsed: n.GPUsUsed,
			Model:    n.Model,
		})
	}
	return writeJSON(w, out)
}

func writeJSON(w io.Writer, v any) error {
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}

func newTabWriter(w io.Writer) *tabwriter.Writer {
	return tabwriter.NewWriter(w, 0, 8, 2, ' ', 0)
}
