package cli

import (
	"fmt"
	"io"

	"example.com/rollout/internal/version"
)

func runVersion(stdout io.Writer) int {
	fmt.Fprintf(stdout, "rollout %s\n", version.Version)
	return 0
}
