// Package duration parses and formats durations such as "1w2d" or "1.5h".
//
// A duration is one or more terms with no spaces between them. A term is a
// decimal number with an optional fraction ("2", "0.25", "1.05") and a unit:
//
//	Unit  Meaning
//	w     week, 7 days
//	d     day, 24 hours
//	h     hour
//	m     minute
//	s     second
//	ms    millisecond
//	us    microsecond
//	ns    nanosecond
//
// The terms must go from the largest unit to the smallest unit, and each unit
// can occur one time only. Thus "1h30m" and "1w2d" are valid, but "30m1h" and
// "1h2h" are not valid.
//
// The fraction applies to the unit of its term: "1.5h" is 1 hour 30 minutes
// and "1.05h" is 1 hour 3 minutes. Fraction digits below one nanosecond are
// discarded.
//
// Format writes a duration in the same format, so Parse(Format(d)) == d.
package duration
