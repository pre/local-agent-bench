// Package inventory reads the node inventory file of a GPU cluster.
//
// Each line that is not empty and is not a "#" comment describes one node:
//
//	gpu-a01  rack=r01 state=ready gpus=8 used=3 model=mi300x
//
// The keys rack, state and gpus are necessary. used is 0 and model is
// empty when they are not given.
package inventory

import (
	"bufio"
	"fmt"
	"io"
	"strconv"
	"strings"
)

// State is the scheduling state of a node.
type State string

const (
	Ready   State = "ready"
	Drained State = "drained"
	Down    State = "down"
)

// ParseState returns the State for s, or an error if s is not a known state.
func ParseState(s string) (State, error) {
	switch st := State(s); st {
	case Ready, Drained, Down:
		return st, nil
	}
	return "", fmt.Errorf("unknown state %q (want ready, drained or down)", s)
}

// Node is one node of the inventory.
type Node struct {
	Name     string
	Rack     string
	State    State
	GPUs     int
	GPUsUsed int
	Model    string
}

// Parse reads an inventory. The nodes keep the order of the file.
func Parse(r io.Reader) ([]Node, error) {
	var nodes []Node
	seen := make(map[string]bool)
	sc := bufio.NewScanner(r)
	lineNo := 0
	for sc.Scan() {
		lineNo++
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		n, err := parseLine(line)
		if err != nil {
			return nil, fmt.Errorf("line %d: %w", lineNo, err)
		}
		if seen[n.Name] {
			return nil, fmt.Errorf("line %d: duplicate node %s", lineNo, n.Name)
		}
		seen[n.Name] = true
		nodes = append(nodes, n)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	return nodes, nil
}

func parseLine(line string) (Node, error) {
	fields := strings.Fields(line)
	n := Node{Name: fields[0]}
	hasGPUs := false
	for _, f := range fields[1:] {
		key, value, ok := strings.Cut(f, "=")
		if !ok {
			return Node{}, fmt.Errorf("expected key=value, found %q", f)
		}
		var err error
		switch key {
		case "rack":
			n.Rack = value
		case "state":
			n.State, err = ParseState(value)
		case "gpus":
			n.GPUs, err = parseCount(key, value)
			hasGPUs = true
		case "used":
			n.GPUsUsed, err = parseCount(key, value)
		case "model":
			n.Model = value
		default:
			err = fmt.Errorf("unknown key %q", key)
		}
		if err != nil {
			return Node{}, err
		}
	}
	switch {
	case n.Rack == "":
		return Node{}, fmt.Errorf("node %s: missing rack", n.Name)
	case n.State == "":
		return Node{}, fmt.Errorf("node %s: missing state", n.Name)
	case !hasGPUs:
		return Node{}, fmt.Errorf("node %s: missing gpus", n.Name)
	case n.GPUsUsed > n.GPUs:
		return Node{}, fmt.Errorf("node %s: used %d is more than gpus %d", n.Name, n.GPUsUsed, n.GPUs)
	}
	return n, nil
}

func parseCount(key, value string) (int, error) {
	v, err := strconv.Atoi(value)
	if err != nil || v < 0 {
		return 0, fmt.Errorf("%s: invalid count %q", key, value)
	}
	return v, nil
}

// Filter selects nodes. An empty field matches all nodes.
type Filter struct {
	State State
	Rack  string
}

// Apply returns the nodes that match f, in their original order.
func (f Filter) Apply(nodes []Node) []Node {
	out := make([]Node, 0, len(nodes))
	for _, n := range nodes {
		if f.State != "" && n.State != f.State {
			continue
		}
		if f.Rack != "" && n.Rack != f.Rack {
			continue
		}
		out = append(out, n)
	}
	return out
}

// FreeGPUs returns the GPUs of n that can take new work. Only a ready node
// has free GPUs.
func (n Node) FreeGPUs() int {
	if n.State != Ready {
		return 0
	}
	return n.GPUs - n.GPUsUsed
}
