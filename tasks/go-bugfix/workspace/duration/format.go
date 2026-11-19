package duration

import (
	"fmt"
	"strings"
	"time"
)

// formatUnits goes from the largest unit to the smallest unit.
var formatUnits = []unit{
	{"w", Week},
	{"d", Day},
	{"h", time.Hour},
	{"m", time.Minute},
	{"s", time.Second},
	{"ms", time.Millisecond},
	{"us", time.Microsecond},
	{"ns", time.Nanosecond},
}

// Format returns d in the format of Parse, with no zero terms, for example
// "1w2d3h". Format(0) is "0s". A negative d gets the prefix "-".
func Format(d time.Duration) string {
	if d == 0 {
		return "0s"
	}
	var b strings.Builder
	if d < 0 {
		b.WriteString("-")
		d = -d
	}
	for _, u := range formatUnits {
		if n := d / u.size; n > 0 {
			fmt.Fprintf(&b, "%d%s", n, u.name)
			d -= n * u.size
		}
	}
	return b.String()
}
