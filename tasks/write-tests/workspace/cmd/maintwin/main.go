// Command maintwin tells if a maintenance window is open, and when it opens
// next. The node drain job calls it before it starts an upgrade.
//
//	maintwin -window "Mon-Fri 22:00-02:00" [-at 2026-11-20T23:30:00+02:00]
package main

import (
	"flag"
	"fmt"
	"os"
	"time"

	"example.com/maintwin/window"
)

func main() {
	spec := flag.String("window", "", "maintenance window spec, for example \"Sat 01:00-05:00\"")
	at := flag.String("at", "", "time to check in RFC 3339 format (default: now)")
	flag.Parse()

	w, err := window.Parse(*spec)
	if err != nil {
		fmt.Fprintln(os.Stderr, "maintwin:", err)
		os.Exit(2)
	}
	t := time.Now()
	if *at != "" {
		if t, err = time.Parse(time.RFC3339, *at); err != nil {
			fmt.Fprintln(os.Stderr, "maintwin: -at:", err)
			os.Exit(2)
		}
	}
	if w.Contains(t) {
		fmt.Println("open")
		return
	}
	fmt.Printf("closed, opens %s for %s\n", w.Next(t).Format(time.RFC3339), w.Duration())
	os.Exit(1)
}
