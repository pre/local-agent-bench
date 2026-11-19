// Command minisql runs one query on the CSV tables of a directory.
//
//	minisql [-data dir] "SELECT ..."
package main

import (
	"flag"
	"fmt"
	"os"

	"example.com/minisql/db"
)

func main() {
	data := flag.String("data", "testdata", "directory with the CSV tables")
	flag.Parse()
	if flag.NArg() != 1 {
		fmt.Fprintln(os.Stderr, `usage: minisql [-data dir] "SELECT ..."`)
		os.Exit(2)
	}
	d, err := db.Open(*data)
	if err != nil {
		fmt.Fprintln(os.Stderr, "minisql:", err)
		os.Exit(1)
	}
	r, err := d.Query(flag.Arg(0))
	if err != nil {
		fmt.Fprintln(os.Stderr, "minisql:", err)
		os.Exit(1)
	}
	fmt.Print(db.Format(r))
}
