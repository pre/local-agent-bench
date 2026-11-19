package cli

import (
	"flag"
	"fmt"
	"io"
	"log"
)

func runCheck(args []string, stdout io.Writer, logger *log.Logger) int {
	fs := flag.NewFlagSet("rollout check", flag.ContinueOnError)
	fs.SetOutput(logger.Writer())
	var in inputFlags
	in.register(fs)
	if err := fs.Parse(args); err != nil {
		return 2
	}
	inv, pol, err := in.load(logger)
	if err != nil {
		logger.Print(err)
		return 1
	}
	fmt.Fprintf(stdout, "inventory: %d nodes in %d racks\n", len(inv.Nodes), len(inv.Racks()))
	fmt.Fprintf(stdout, "policy: batches of %d nodes, %d per rack, %d canaries\n",
		pol.MaxBatchSize, pol.MaxUnavailablePerRack, pol.Canary.Count)
	return 0
}
