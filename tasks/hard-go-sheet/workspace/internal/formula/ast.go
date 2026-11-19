// Package formula parses the formula language of the sheet (see
// docs/ENGINE.md, section "Formulas").
package formula

import (
	"example.com/sheet/internal/addr"
)

// Expr is a node of the syntax tree of a formula.
type Expr interface {
	exprNode()
}

// NumberLit is a number such as 2.5.
type NumberLit struct{ Val float64 }

// TextLit is a text in double quotes.
type TextLit struct{ Val string }

// BoolLit is TRUE or FALSE.
type BoolLit struct{ Val bool }

// Ref is a reference to one cell.
type Ref struct{ Addr addr.Addr }

// RangeRef is a range of cells. It is permitted only as a function argument.
type RangeRef struct{ Range addr.Range }

// Unary is a prefix operator: "-" or "+".
type Unary struct {
	Op string
	X  Expr
}

// Binary is an infix operator: + - * / ^ & = <> < <= > >=.
type Binary struct {
	Op   string
	L, R Expr
}

// Call is a function call. Name is in upper case.
type Call struct {
	Name string
	Args []Expr
}

func (*NumberLit) exprNode() {}
func (*TextLit) exprNode()   {}
func (*BoolLit) exprNode()   {}
func (*Ref) exprNode()       {}
func (*RangeRef) exprNode()  {}
func (*Unary) exprNode()     {}
func (*Binary) exprNode()    {}
func (*Call) exprNode()      {}

// Refs gives each cell that the formula text refers to: single references
// and each cell of each range, in both branches of IF. Each cell is in the
// result once, in the order of its first occurrence.
func Refs(e Expr) []addr.Addr {
	var out []addr.Addr
	seen := map[addr.Addr]bool{}
	add := func(a addr.Addr) {
		if !seen[a] {
			seen[a] = true
			out = append(out, a)
		}
	}
	Walk(e, func(n Expr) {
		switch n := n.(type) {
		case *Ref:
			add(n.Addr)
		case *RangeRef:
			for _, a := range n.Range.Cells() {
				add(a)
			}
		}
	})
	return out
}

// Walk calls fn for e and for each node below e, parents first.
func Walk(e Expr, fn func(Expr)) {
	fn(e)
	switch n := e.(type) {
	case *Unary:
		Walk(n.X, fn)
	case *Binary:
		Walk(n.L, fn)
		Walk(n.R, fn)
	case *Call:
		for _, a := range n.Args {
			Walk(a, fn)
		}
	}
}
