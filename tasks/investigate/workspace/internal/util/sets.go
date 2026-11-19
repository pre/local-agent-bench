package util

import "sort"

// StringSet is a set of strings.
type StringSet map[string]struct{}

// NewStringSet returns a set that holds items.
func NewStringSet(items ...string) StringSet {
	s := make(StringSet, len(items))
	for _, item := range items {
		s[item] = struct{}{}
	}
	return s
}

// Add adds item to the set.
func (s StringSet) Add(item string) {
	s[item] = struct{}{}
}

// Has reports whether item is in the set.
func (s StringSet) Has(item string) bool {
	_, ok := s[item]
	return ok
}

// Sorted returns the items in sorted order.
func (s StringSet) Sorted() []string {
	out := make([]string, 0, len(s))
	for item := range s {
		out = append(out, item)
	}
	sort.Strings(out)
	return out
}
