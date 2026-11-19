// Command dur adds durations and prints the total.
//
//	dur 1h30m 45m    prints 2h15m
package main

import (
	"fmt"
	"io"
	"os"
	"time"

	"example.com/dur/duration"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprintln(stderr, "usage: dur DURATION...")
		return 2
	}
	var total time.Duration
	for _, a := range args {
		d, err := duration.Parse(a)
		if err != nil {
			fmt.Fprintf(stderr, "dur: %v\n", err)
			return 1
		}
		total += d
	}
	fmt.Fprintln(stdout, duration.Format(total))
	return 0
}
