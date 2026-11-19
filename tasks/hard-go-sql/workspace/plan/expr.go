// Package plan checks a parsed query against the tables and builds the plan
// that the package exec runs.
package plan

import "example.com/minisql/value"

// Expr is a checked expression. Type is its type; value.Null only for the
// NULL literal.
type Expr interface {
	Type() value.Type
}

// Const is a constant.
type Const struct{ V value.Value }

// Col reads the column Index of the input row.
type Col struct {
	Index int
	Name  string
	T     value.Type
}

// Unary is "-" or "NOT".
type Unary struct {
	Op string
	X  Expr
	T  value.Type
}

// Binary is an infix operator of the SQL dialect.
type Binary struct {
	Op   string
	L, R Expr
	T    value.Type
}

// IsNull is "IS NULL" or "IS NOT NULL".
type IsNull struct {
	X   Expr
	Not bool
}

// Func is a call of a scalar function.
type Func struct {
	Name string
	Args []Expr
	T    value.Type
}

func (c *Const) Type() value.Type  { return c.V.Type() }
func (c *Col) Type() value.Type    { return c.T }
func (u *Unary) Type() value.Type  { return u.T }
func (b *Binary) Type() value.Type { return b.T }
func (*IsNull) Type() value.Type   { return value.Bool }
func (f *Func) Type() value.Type   { return f.T }
