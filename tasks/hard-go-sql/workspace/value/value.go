// Package value has the SQL values and types of minisql.
package value

import (
	"fmt"
	"math"
	"strconv"
	"strings"
)

// Type is the type of a column or an expression.
type Type uint8

const (
	Null Type = iota // only the literal NULL has this type
	Int
	Float
	Text
	Bool
)

func (t Type) String() string {
	switch t {
	case Null:
		return "NULL"
	case Int:
		return "INT"
	case Float:
		return "FLOAT"
	case Text:
		return "TEXT"
	case Bool:
		return "BOOL"
	}
	return fmt.Sprintf("Type(%d)", t)
}

// ParseType reads a type name, not case sensitive.
func ParseType(s string) (Type, bool) {
	switch strings.ToUpper(s) {
	case "INT":
		return Int, true
	case "FLOAT":
		return Float, true
	case "TEXT":
		return Text, true
	case "BOOL":
		return Bool, true
	}
	return Null, false
}

// Numeric tells if t is INT or FLOAT.
func (t Type) Numeric() bool { return t == Int || t == Float }

// Value is one SQL value. The zero Value is NULL.
type Value struct {
	typ Type
	i   int64
	f   float64
	s   string
}

var NullValue = Value{}

func NewInt(i int64) Value     { return Value{typ: Int, i: i} }
func NewFloat(f float64) Value { return Value{typ: Float, f: f} }
func NewText(s string) Value   { return Value{typ: Text, s: s} }
func NewBool(b bool) Value {
	if b {
		return Value{typ: Bool, i: 1}
	}
	return Value{typ: Bool}
}

func (v Value) Type() Type     { return v.typ }
func (v Value) IsNull() bool   { return v.typ == Null }
func (v Value) Int() int64     { return v.i }
func (v Value) Float() float64 { return v.f }
func (v Value) Text() string   { return v.s }
func (v Value) Bool() bool     { return v.i != 0 }

// AsFloat gives the value of an INT or a FLOAT as float64.
func (v Value) AsFloat() float64 {
	if v.typ == Int {
		return float64(v.i)
	}
	return v.f
}

// Compare orders two values that are not NULL and that have comparable
// types: two numbers (INT and FLOAT compare by their numeric value), two
// texts (byte order) or two bools (FALSE < TRUE).
func Compare(a, b Value) int {
	switch {
	case a.typ == Int && b.typ == Int:
		return cmp3(a.i < b.i, a.i > b.i)
	case a.typ.Numeric() && b.typ.Numeric():
		x, y := a.AsFloat(), b.AsFloat()
		return cmp3(x < y, x > y)
	case a.typ == Text:
		return strings.Compare(a.s, b.s)
	}
	return cmp3(a.i < b.i, a.i > b.i)
}

func cmp3(less, greater bool) int {
	switch {
	case less:
		return -1
	case greater:
		return 1
	}
	return 0
}

// Identical tells if two values are the same for DISTINCT and for grouping:
// two NULLs are identical, and other values are identical when Compare gives
// 0. Thus 0.0 and -0.0 are identical.
func Identical(a, b Value) bool {
	if a.IsNull() || b.IsNull() {
		return a.IsNull() && b.IsNull()
	}
	return Compare(a, b) == 0
}

// Key gives a text that is equal for two values exactly when they are
// Identical and have the same type. It is for use as a map key.
func (v Value) Key() string {
	switch v.typ {
	case Null:
		return "n"
	case Int:
		return "i" + strconv.FormatInt(v.i, 10)
	case Float:
		f := v.f
		if f == 0 {
			f = 0 // -0.0 and 0.0 have the same key
		}
		return "f" + strconv.FormatUint(math.Float64bits(f), 16)
	case Text:
		return "t" + v.s
	}
	return "b" + strconv.FormatInt(v.i, 10)
}

// String formats a value for output. NULL is "NULL". A FLOAT has at least one
// digit after the point and at most 6 (rounded, trailing zeros removed):
// 2.5, 3.0, 0.333333.
func (v Value) String() string {
	switch v.typ {
	case Null:
		return "NULL"
	case Int:
		return strconv.FormatInt(v.i, 10)
	case Float:
		return FormatFloat(v.f)
	case Text:
		return v.s
	}
	if v.Bool() {
		return "TRUE"
	}
	return "FALSE"
}

// FormatFloat formats a FLOAT value (see Value.String).
func FormatFloat(f float64) string {
	s := strconv.FormatFloat(f, 'f', 6, 64)
	s = strings.TrimRight(s, "0")
	if strings.HasSuffix(s, ".") {
		s += "0"
	}
	if s == "-0.0" {
		s = "0.0"
	}
	return s
}
