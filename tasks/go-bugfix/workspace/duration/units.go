package duration

import (
	"sort"
	"time"
)

// Day and Week are the units that package time does not have.
const (
	Day  = 24 * time.Hour
	Week = 7 * Day
)

type unit struct {
	name string
	size time.Duration
}

// units is sorted by name, so lookup can use a binary search.
var units = []unit{
	{"d", Day},
	{"h", time.Hour},
	{"m", time.Minute},
	{"ms", time.Millisecond},
	{"ns", time.Nanosecond},
	{"s", time.Second},
	{"us", time.Microsecond},
	{"w", Week},
}

// lookup returns the unit with the given name and its position in units.
func lookup(name string) (unit, int, bool) {
	i := sort.Search(len(units), func(i int) bool { return units[i].name >= name })
	if i < len(units) && units[i].name == name {
		return units[i], i, true
	}
	return unit{}, -1, false
}
