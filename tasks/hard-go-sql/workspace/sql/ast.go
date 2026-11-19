// Package sql parses the SQL dialect of minisql (see docs/SQL.md).
package sql

import (
	"fmt"
	"strings"

	"example.com/minisql/value"
)

// Error is the error type of minisql. Code is one of the codes in
// docs/SQL.md, section "Errors".
type Error struct {
	Code string
	Msg  string
}

func (e *Error) Error() string { return e.Code + ": " + e.Msg }

// Errorf makes an *Error.
func Errorf(code, format string, args ...any) *Error {
	return &Error{Code: code, Msg: fmt.Sprintf(format, args...)}
}

// Select is a parsed SELECT statement.
type Select struct {
	Items   []SelectItem
	From    string
	Where   Expr // nil: no WHERE
	OrderBy []OrderItem
	Limit   int64 // -1: no LIMIT
	Offset  int64
}

// SelectItem is "*" or an expression with an optional alias.
type SelectItem struct {
	Star  bool
	Expr  Expr
	Alias string
}

// OrderItem is one expression of ORDER BY.
type OrderItem struct {
	Expr Expr
	Desc bool
}

// Expr is an expression. String gives its canonical text, which is also the
// name of an output column without alias (see docs/SQL.md).
type Expr interface {
	String() string
	exprNode()
}

// Literal is a constant: a number, a text, TRUE, FALSE or NULL.
type Literal struct{ Value value.Value }

// ColumnRef is a column name as written in the query.
type ColumnRef struct{ Name string }

// Unary is "-x" or "NOT x".
type Unary struct {
	Op string
	X  Expr
}

// Binary is an infix operator: OR AND = <> < <= > >= || + - * / %.
type Binary struct {
	Op   string
	L, R Expr
}

// IsNull is "x IS NULL" or "x IS NOT NULL".
type IsNull struct {
	X   Expr
	Not bool
}

// Call is a function call. Name is upper case. Star is true for "F(*)".
type Call struct {
	Name string
	Args []Expr
	Star bool
}

func (*Literal) exprNode()   {}
func (*ColumnRef) exprNode() {}
func (*Unary) exprNode()     {}
func (*Binary) exprNode()    {}
func (*IsNull) exprNode()    {}
func (*Call) exprNode()      {}

func (l *Literal) String() string {
	if l.Value.Type() == value.Text {
		return "'" + strings.ReplaceAll(l.Value.Text(), "'", "''") + "'"
	}
	return l.Value.String()
}

func (c *ColumnRef) String() string { return c.Name }

func (u *Unary) String() string {
	if u.Op == "NOT" {
		return "NOT " + operand(u.X)
	}
	return u.Op + operand(u.X)
}

func (b *Binary) String() string {
	return operand(b.L) + " " + b.Op + " " + operand(b.R)
}

func (n *IsNull) String() string {
	if n.Not {
		return operand(n.X) + " IS NOT NULL"
	}
	return operand(n.X) + " IS NULL"
}

func (c *Call) String() string {
	if c.Star {
		return c.Name + "(*)"
	}
	parts := make([]string, len(c.Args))
	for i, a := range c.Args {
		parts[i] = a.String()
	}
	return c.Name + "(" + strings.Join(parts, ", ") + ")"
}

// operand puts an operand in parentheses when it is an operator expression.
func operand(e Expr) string {
	switch e.(type) {
	case *Binary, *Unary, *IsNull:
		return "(" + e.String() + ")"
	}
	return e.String()
}

// Walk calls fn for e and each expression below e, parents first.
func Walk(e Expr, fn func(Expr)) {
	if e == nil {
		return
	}
	fn(e)
	switch n := e.(type) {
	case *Unary:
		Walk(n.X, fn)
	case *Binary:
		Walk(n.L, fn)
		Walk(n.R, fn)
	case *IsNull:
		Walk(n.X, fn)
	case *Call:
		for _, a := range n.Args {
			Walk(a, fn)
		}
	}
}
