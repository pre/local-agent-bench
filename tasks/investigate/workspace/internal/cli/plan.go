package cli

import (
	"flag"
	"io"
	"log"

	"example.com/rollout/internal/plan"
)

func runPlan(args []string, stdout io.Writer, logger *log.Logger) int {
	fs := flag.NewFlagSet("rollout plan", flag.ContinueOnError)
	fs.SetOutput(logger.Writer())
	var in inputFlags
	in.register(fs)
	format := fs.String("o", "text", "output `format`: text or json")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *format != "text" && *format != "json" {
		logger.Printf("unknown output format %q", *format)
		return 2
	}

	inv, pol, err := in.load(logger)
	if err != nil {
		logger.Print(err)
		return 1
	}
	p, err := plan.Build(inv, pol)
	if err != nil {
		logger.Print(err)
		return 1
	}
	logger.Printf("%d nodes in %d batches, %d skipped", p.NodeCount(), len(p.Batches), len(p.Skipped))
	if err := plan.Validate(p, pol); err != nil {
		logger.Printf("plan is not valid: %v", err)
		return 1
	}

	if *format == "json" {
		err = plan.WriteJSON(stdout, p)
	} else {
		err = plan.WriteText(stdout, p)
	}
	if err != nil {
		logger.Print(err)
		return 1
	}
	return 0
}
