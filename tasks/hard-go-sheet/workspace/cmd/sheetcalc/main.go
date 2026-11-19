// Command sheetcalc loads a sheet, applies edits and prints the changes of
// watched cells.
//
//	sheetcalc [-watch A1,B7] [-all] sheet-file [edit-file]
//
// The sheet file is loaded as one update. Each group of the edit file is one
// more update. For each update, sheetcalc prints a line for each watched cell
// that changed: "update 3: B7 12 -> 15". With -all it prints the value of
// each cell at the end.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"example.com/sheet/engine"
	"example.com/sheet/internal/sheetfile"
	"example.com/sheet/value"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("sheetcalc", flag.ContinueOnError)
	fs.SetOutput(stderr)
	watch := fs.String("watch", "", "comma separated cells to watch")
	all := fs.Bool("all", false, "print the value of each cell at the end")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if fs.NArg() < 1 || fs.NArg() > 2 {
		fmt.Fprintln(stderr, "usage: sheetcalc [-watch A1,B7] [-all] sheet-file [edit-file]")
		return 2
	}

	sheet := engine.New()
	update := 0
	if *watch != "" {
		for _, c := range strings.Split(*watch, ",") {
			c = strings.TrimSpace(c)
			err := sheet.Watch(c, func(cell string, old, new value.Value) {
				fmt.Fprintf(stdout, "update %d: %s %s -> %s\n", update, cell, show(old), show(new))
			})
			if err != nil {
				fmt.Fprintf(stderr, "sheetcalc: -watch: %v\n", err)
				return 2
			}
		}
	}

	groups, err := sheetfile.ReadFile(fs.Arg(0))
	if err != nil {
		fmt.Fprintf(stderr, "sheetcalc: %v\n", err)
		return 1
	}
	if err := sheet.Apply(sheetfile.Flatten(groups)); err != nil {
		fmt.Fprintf(stderr, "sheetcalc: %s: %v\n", fs.Arg(0), err)
		return 1
	}

	if fs.NArg() == 2 {
		edits, err := sheetfile.ReadFile(fs.Arg(1))
		if err != nil {
			fmt.Fprintf(stderr, "sheetcalc: %v\n", err)
			return 1
		}
		for i, g := range edits {
			update = i + 1
			if err := sheet.Apply(g); err != nil {
				fmt.Fprintf(stderr, "sheetcalc: update %d: %v\n", update, err)
				return 1
			}
		}
	}

	if *all {
		for _, c := range sheet.Cells() {
			fmt.Fprintf(stdout, "%s = %s\n", c, show(sheet.Value(c)))
		}
	}
	return 0
}

func show(v value.Value) string {
	if v.Kind() == value.KindEmpty {
		return "(empty)"
	}
	if v.Kind() == value.KindText {
		return fmt.Sprintf("%q", v.Str())
	}
	return v.String()
}
