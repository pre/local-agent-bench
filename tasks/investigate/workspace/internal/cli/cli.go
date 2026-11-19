// Package cli implements the rollout command line.
package cli

import (
	"fmt"
	"io"
	"log"
)

const usage = `Usage: rollout <command> [flags]

Commands:
  plan     print the upgrade batches for an inventory
  check    check an inventory file and a policy file
  version  print the version
`

// Main runs rollout with the arguments args (without the program name) and
// returns the exit code.
func Main(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	logger := log.New(stderr, "rollout: ", log.Lshortfile)
	switch args[0] {
	case "plan":
		return runPlan(args[1:], stdout, logger)
	case "check":
		return runCheck(args[1:], stdout, logger)
	case "version":
		return runVersion(stdout)
	case "help", "-h", "--help":
		fmt.Fprint(stdout, usage)
		return 0
	}
	fmt.Fprintf(stderr, "rollout: unknown command %q\n", args[0])
	fmt.Fprint(stderr, usage)
	return 2
}
