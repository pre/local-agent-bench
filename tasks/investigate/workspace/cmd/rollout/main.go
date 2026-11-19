// Command rollout plans the batches of a rolling upgrade of cluster nodes.
package main

import (
	"os"

	"example.com/rollout/internal/cli"
)

func main() {
	os.Exit(cli.Main(os.Args[1:], os.Stdout, os.Stderr))
}
