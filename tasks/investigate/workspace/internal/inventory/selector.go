package inventory

import (
	"fmt"
	"strings"
)

// Selector selects nodes by their labels. It is the AND of its terms.
// The text form is a comma-separated list of terms:
//
//	key=value   the label key has the value
//	key!=value  the label key does not have the value (or is missing)
//	key         the node has the label key
//	!key        the node does not have the label key
//
// An empty selector selects all nodes.
type Selector struct {
	terms []term
}

type termOp int

const (
	opEquals termOp = iota
	opNotEquals
	opExists
	opNotExists
)

type term struct {
	op    termOp
	key   string
	value string
}

// ParseSelector parses the text form of a selector.
func ParseSelector(text string) (Selector, error) {
	var sel Selector
	text = strings.TrimSpace(text)
	if text == "" {
		return sel, nil
	}
	for _, raw := range strings.Split(text, ",") {
		raw = strings.TrimSpace(raw)
		var t term
		switch {
		case strings.Contains(raw, "!="):
			key, value, _ := strings.Cut(raw, "!=")
			t = term{op: opNotEquals, key: key, value: value}
		case strings.Contains(raw, "="):
			key, value, _ := strings.Cut(raw, "=")
			t = term{op: opEquals, key: key, value: value}
		case strings.HasPrefix(raw, "!"):
			t = term{op: opNotExists, key: raw[1:]}
		default:
			t = term{op: opExists, key: raw}
		}
		t.key = strings.TrimSpace(t.key)
		t.value = strings.TrimSpace(t.value)
		if t.key == "" {
			return Selector{}, fmt.Errorf("selector %q: empty key in term %q", text, raw)
		}
		sel.terms = append(sel.terms, t)
	}
	return sel, nil
}

// Matches reports whether n has all terms of the selector.
func (s Selector) Matches(n Node) bool {
	for _, t := range s.terms {
		v, ok := n.Label(t.key)
		var match bool
		switch t.op {
		case opEquals:
			match = ok && v == t.value
		case opNotEquals:
			match = !ok || v != t.value
		case opExists:
			match = ok
		case opNotExists:
			match = !ok
		}
		if !match {
			return false
		}
	}
	return true
}

// Empty reports whether the selector has no terms.
func (s Selector) Empty() bool {
	return len(s.terms) == 0
}
