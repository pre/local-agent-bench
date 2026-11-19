package duration

import (
	"fmt"
	"strings"
)

// term is one number and unit pair of a duration, for example "1.5h".
type term struct {
	whole string // digits before the decimal point
	frac  string // digits after the decimal point, can be empty
	unit  string
}

// split separates s into its terms.
func split(s string) ([]term, error) {
	var terms []term
	for s != "" {
		var t term
		t.whole, s = digits(s)
		if strings.HasPrefix(s, ".") {
			t.frac, s = digits(s[1:])
		}
		if t.whole == "" && t.frac == "" {
			return nil, fmt.Errorf("expected a number at %q", s)
		}
		t.unit, s = letters(s)
		if t.unit == "" {
			return nil, fmt.Errorf("missing unit after %q", t.whole)
		}
		terms = append(terms, t)
	}
	return terms, nil
}

// digits returns the leading digits of s and the rest of s.
// Leading zeros are not significant, so digits removes them.
func digits(s string) (string, string) {
	i := 0
	for i < len(s) && s[i] >= '0' && s[i] <= '9' {
		i++
	}
	d := strings.TrimLeft(s[:i], "0")
	if d == "" && i > 0 {
		d = "0"
	}
	return d, s[i:]
}

// letters returns the leading ASCII letters of s and the rest of s.
func letters(s string) (string, string) {
	i := 0
	for i < len(s) && (s[i] >= 'a' && s[i] <= 'z' || s[i] >= 'A' && s[i] <= 'Z') {
		i++
	}
	return s[:i], s[i:]
}
