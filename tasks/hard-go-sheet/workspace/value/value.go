// Package value has the values of spreadsheet cells.
package value

import (
	"math"
	"strconv"
)

// Kind is the type of a value.
type Kind uint8

const (
	KindEmpty Kind = iota
	KindNumber
	KindText
	KindBool
	KindError
)

func (k Kind) String() string {
	switch k {
	case KindEmpty:
		return "empty"
	case KindNumber:
		return "number"
	case KindText:
		return "text"
	case KindBool:
		return "bool"
	case KindError:
		return "error"
	}
	return "kind(" + strconv.Itoa(int(k)) + ")"
}

// The error codes of formula results.
const (
	ErrDivZero = "#DIV/0!" // division by zero
	ErrValue   = "#VALUE!" // an operand has the wrong type
	ErrName    = "#NAME?"  // unknown function
	ErrNum     = "#NUM!"   // the result is not a finite number
)

// Value is the value of a cell. The zero Value is the empty value.
type Value struct {
	kind Kind
	num  float64
	str  string // text, or the code of an error
}

// Empty is the value of a cell without input.
var Empty = Value{}

// Number gives a number value. A value that is not finite gives the error #NUM!.
func Number(f float64) Value {
	if math.IsNaN(f) || math.IsInf(f, 0) {
		return Error(ErrNum)
	}
	return Value{kind: KindNumber, num: f}
}

// Text gives a text value.
func Text(s string) Value { return Value{kind: KindText, str: s} }

// Boolean gives a bool value.
func Boolean(b bool) Value {
	if b {
		return Value{kind: KindBool, num: 1}
	}
	return Value{kind: KindBool}
}

// Error gives an error value with a code such as ErrDivZero.
func Error(code string) Value { return Value{kind: KindError, str: code} }

func (v Value) Kind() Kind    { return v.kind }
func (v Value) IsError() bool { return v.kind == KindError }
func (v Value) Num() float64  { return v.num }
func (v Value) Str() string   { return v.str }
func (v Value) Bool() bool    { return v.kind == KindBool && v.num != 0 }
func (v Value) ErrCode() string {
	if v.kind == KindError {
		return v.str
	}
	return ""
}

// Equal tells if two values are the same: the same kind and the same content.
// Numbers are compared with ==, so 0 and -0 are equal. Two errors are equal
// when they have the same code.
func (v Value) Equal(w Value) bool {
	if v.kind != w.kind {
		return false
	}
	switch v.kind {
	case KindNumber, KindBool:
		return v.num == w.num
	case KindText, KindError:
		return v.str == w.str
	}
	return true
}

// String formats the value for output: numbers in the shortest form that
// reads back to the same number, bools as TRUE and FALSE, errors as their
// code, the empty value as "".
func (v Value) String() string {
	switch v.kind {
	case KindNumber:
		return strconv.FormatFloat(v.num, 'g', -1, 64)
	case KindText, KindError:
		return v.str
	case KindBool:
		if v.Bool() {
			return "TRUE"
		}
		return "FALSE"
	}
	return ""
}
