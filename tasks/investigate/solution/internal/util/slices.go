// Package util holds small helpers that several packages use.
package util

// Filter returns the elements of s for which keep returns true, in their
// original order. It does not change s.
func Filter[T any](s []T, keep func(T) bool) []T {
	var out []T
	for _, v := range s {
		if keep(v) {
			out = append(out, v)
		}
	}
	return out
}

// Map returns the result of f for each element of s.
func Map[T, U any](s []T, f func(T) U) []U {
	out := make([]U, len(s))
	for i, v := range s {
		out[i] = f(v)
	}
	return out
}

// Chunk splits s into parts of at most size elements.
func Chunk[T any](s []T, size int) [][]T {
	if size <= 0 {
		return [][]T{s}
	}
	var parts [][]T
	for len(s) > size {
		parts = append(parts, s[:size:size])
		s = s[size:]
	}
	if len(s) > 0 {
		parts = append(parts, s)
	}
	return parts
}
