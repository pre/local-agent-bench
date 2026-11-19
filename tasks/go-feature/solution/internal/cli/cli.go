// Package cli implements the nodeinv command line.
package cli

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"

	"example.com/nodeinv/internal/inventory"
	"example.com/nodeinv/internal/output"
)

const usage = `Usage: nodeinv -f <inventory> [flags]

Lists the nodes of an inventory file.

Flags:
`

// Run runs nodeinv with the command line arguments args (without the program
// name) and returns the exit code.
func Run(args []string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("nodeinv", flag.ContinueOnError)
	fs.SetOutput(stderr)
	fs.Usage = func() {
		fmt.Fprint(stderr, usage)
		fs.PrintDefaults()
	}
	file := fs.String("f", "", "inventory `file` (necessary)")
	state := fs.String("state", "", "show only nodes in this `state` (ready, drained, down)")
	rack := fs.String("rack", "", "show only nodes in this `rack`")
	format := fs.String("o", "table", "output `format`: table or json")
	byRack := fs.Bool("by-rack", false, "show node and GPU counts for each rack instead of the nodes")

	if err := fs.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if fs.NArg() > 0 {
		fmt.Fprintf(stderr, "nodeinv: unexpected argument %q\n", fs.Arg(0))
		return 2
	}
	if *file == "" {
		fmt.Fprintln(stderr, "nodeinv: -f is necessary")
		return 2
	}

	filter := inventory.Filter{Rack: *rack}
	if *state != "" {
		st, err := inventory.ParseState(*state)
		if err != nil {
			fmt.Fprintf(stderr, "nodeinv: -state: %v\n", err)
			return 2
		}
		filter.State = st
	}
	f, err := output.ParseFormat(*format)
	if err != nil {
		fmt.Fprintf(stderr, "nodeinv: -o: %v\n", err)
		return 2
	}

	nodes, err := load(*file)
	if err != nil {
		fmt.Fprintf(stderr, "nodeinv: %v\n", err)
		return 1
	}
	selected := filter.Apply(nodes)
	if *byRack {
		err = output.WriteRacks(stdout, f, inventory.SummarizeRacks(selected))
	} else {
		err = output.WriteNodes(stdout, f, selected)
	}
	if err != nil {
		fmt.Fprintf(stderr, "nodeinv: %v\n", err)
		return 1
	}
	return 0
}

func load(path string) ([]inventory.Node, error) {
	fh, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer fh.Close()
	nodes, err := inventory.Parse(fh)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return nodes, nil
}
