package duration

import (
	"errors"
	"fmt"
	"math"
	"strconv"
	"time"
)

// Parse returns the duration that s describes. The package documentation
// gives the format.
func Parse(s string) (time.Duration, error) {
	if s == "" {
		return 0, errors.New("empty duration")
	}
	terms, err := split(s)
	if err != nil {
		return 0, err
	}
	var total time.Duration
	prev := -1
	for _, t := range terms {
		u, pos, ok := lookup(t.unit)
		if !ok {
			return 0, fmt.Errorf("unknown unit %q", t.unit)
		}
		if pos <= prev {
			return 0, fmt.Errorf("units out of order at %q", t.unit)
		}
		prev = pos
		v, err := value(t, u.size)
		if err != nil {
			return 0, err
		}
		total += v
	}
	return total, nil
}

// value returns the duration of one term with a unit of the given size.
func value(t term, size time.Duration) (time.Duration, error) {
	whole, err := strconv.ParseInt("0"+t.whole, 10, 64)
	if err != nil || whole > math.MaxInt64/int64(size) {
		return 0, fmt.Errorf("number too large: %s", t.whole)
	}
	v := time.Duration(whole) * size

	// Keep only the fraction digits that give whole nanoseconds. Then
	// size/scale is exact and frac*(size/scale) is less than size.
	n, scale := 0, int64(1)
	for n < len(t.frac) && int64(size)%(scale*10) == 0 {
		n, scale = n+1, scale*10
	}
	if frac := t.frac[:n]; frac != "" {
		f, _ := strconv.ParseInt(frac, 10, 64)
		v += time.Duration(f) * (size / time.Duration(scale))
	}
	return v, nil
}
