// Command nodeinv lists the nodes of a GPU cluster inventory file.
package main

import (
	"os"

	"example.com/nodeinv/internal/cli"
)

func main() {
	os.Exit(cli.Run(os.Args[1:], os.Stdout, os.Stderr))
}
