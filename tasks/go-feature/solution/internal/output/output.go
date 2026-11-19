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

// WriteRacks writes rack summaries in the format f. The table ends with a
// TOTAL row.
func WriteRacks(w io.Writer, f Format, racks []inventory.RackSummary) error {
	if f == JSON {
		return writeRacksJSON(w, racks)
	}
	return writeRacksTable(w, racks)
}

func writeRacksTable(w io.Writer, racks []inventory.RackSummary) error {
	tw := newTabWriter(w)
	fmt.Fprintln(tw, "RACK\tNODES\tREADY\tGPUS\tFREE")
	total := inventory.RackSummary{Rack: "TOTAL"}
	for _, r := range racks {
		writeRackRow(tw, r)
		total.Nodes += r.Nodes
		total.Ready += r.Ready
		total.GPUs += r.GPUs
		total.Free += r.Free
	}
	writeRackRow(tw, total)
	return tw.Flush()
}

func writeRackRow(w io.Writer, r inventory.RackSummary) {
	fmt.Fprintf(w, "%s\t%d\t%d\t%d\t%d\n", r.Rack, r.Nodes, r.Ready, r.GPUs, r.Free)
}

type jsonRack struct {
	Rack  string `json:"rack"`
	Nodes int    `json:"nodes"`
	Ready int    `json:"ready"`
	GPUs  int    `json:"gpus"`
	Free  int    `json:"free"`
}

func writeRacksJSON(w io.Writer, racks []inventory.RackSummary) error {
	out := make([]jsonRack, 0, len(racks))
	for _, r := range racks {
		out = append(out, jsonRack(r))
	}
	return writeJSON(w, out)
}
