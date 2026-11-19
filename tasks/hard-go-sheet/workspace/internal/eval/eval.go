// Package eval computes the value of a parsed formula.
package eval

import (
	"math"
	"strings"

	"example.com/sheet/internal/addr"
	"example.com/sheet/internal/formula"
	"example.com/sheet/value"
)

// Func is a custom function. It gets the values of its arguments. A range
// argument gives the values of its cells, by row, then by column.
type Func func(args []value.Value) value.Value

// Env is the environment of one evaluation.
type Env struct {
	// Read gives the current value of a cell. Eval calls it for each cell
	// that the evaluation reads, in the order of the reads.
	Read func(a addr.Addr) value.Value
	// Funcs has the custom functions, with upper case names.
	Funcs map[string]Func
}

// Eval computes the value of e. Errors in the formula give error values,
// not Go errors.
func Eval(e formula.Expr, env *Env) value.Value {
	switch n := e.(type) {
	case *formula.NumberLit:
		return value.Number(n.Val)
	case *formula.TextLit:
		return value.Text(n.Val)
	case *formula.BoolLit:
		return value.Boolean(n.Val)
	case *formula.Ref:
		return env.Read(n.Addr)
	case *formula.RangeRef:
		return value.Error(value.ErrValue) // the parser permits ranges only as arguments
	case *formula.Unary:
		x := Eval(n.X, env)
		f, errv := toNumber(x)
		if errv != nil {
			return *errv
		}
		if n.Op == "-" {
			return value.Number(-f)
		}
		return value.Number(f)
	case *formula.Binary:
		return evalBinary(n, env)
	case *formula.Call:
		return evalCall(n, env)
	}
	return value.Error(value.ErrValue)
}

func evalBinary(n *formula.Binary, env *Env) value.Value {
	l := Eval(n.L, env)
	r := Eval(n.R, env)
	if l.IsError() {
		return l
	}
	if r.IsError() {
		return r
	}
	switch n.Op {
	case "&":
		return value.Text(toText(l) + toText(r))
	case "=", "<>", "<", "<=", ">", ">=":
		c := compare(l, r)
		switch n.Op {
		case "=":
			return value.Boolean(c == 0)
		case "<>":
			return value.Boolean(c != 0)
		case "<":
			return value.Boolean(c < 0)
		case "<=":
			return value.Boolean(c <= 0)
		case ">":
			return value.Boolean(c > 0)
		}
		return value.Boolean(c >= 0)
	}
	a, errv := toNumber(l)
	if errv != nil {
		return *errv
	}
	b, errv := toNumber(r)
	if errv != nil {
		return *errv
	}
	switch n.Op {
	case "+":
		return value.Number(a + b)
	case "-":
		return value.Number(a - b)
	case "*":
		return value.Number(a * b)
	case "/":
		if b == 0 {
			return value.Error(value.ErrDivZero)
		}
		return value.Number(a / b)
	case "^":
		return value.Number(math.Pow(a, b))
	}
	return value.Error(value.ErrValue)
}

// toNumber converts an operand of an arithmetic operator. The empty value is
// 0, TRUE is 1, FALSE is 0. Text gives #VALUE!.
func toNumber(v value.Value) (float64, *value.Value) {
	switch v.Kind() {
	case value.KindEmpty:
		return 0, nil
	case value.KindNumber, value.KindBool:
		return v.Num(), nil
	case value.KindError:
		return 0, &v
	}
	e := value.Error(value.ErrValue)
	return 0, &e
}

func toText(v value.Value) string {
	return v.String()
}

// toBool converts the condition of IF and the arguments of AND, OR and NOT.
func toBool(v value.Value) (bool, *value.Value) {
	switch v.Kind() {
	case value.KindEmpty:
		return false, nil
	case value.KindBool, value.KindNumber:
		return v.Num() != 0, nil
	case value.KindError:
		return false, &v
	}
	e := value.Error(value.ErrValue)
	return false, &e
}

// compare orders two values that are not errors. The empty value takes the
// zero value of the kind of the other operand. Values of different kinds
// order as number < text < bool.
func compare(l, r value.Value) int {
	if l.Kind() == value.KindEmpty {
		l = zeroOf(r.Kind())
	}
	if r.Kind() == value.KindEmpty {
		r = zeroOf(l.Kind())
	}
	if l.Kind() != r.Kind() {
		return rank(l.Kind()) - rank(r.Kind())
	}
	switch l.Kind() {
	case value.KindNumber, value.KindBool:
		switch {
		case l.Num() < r.Num():
			return -1
		case l.Num() > r.Num():
			return 1
		}
		return 0
	case value.KindText:
		return strings.Compare(l.Str(), r.Str())
	}
	return 0
}

func zeroOf(k value.Kind) value.Value {
	switch k {
	case value.KindText:
		return value.Text("")
	case value.KindBool:
		return value.Boolean(false)
	}
	return value.Number(0)
}

func rank(k value.Kind) int {
	switch k {
	case value.KindText:
		return 1
	case value.KindBool:
		return 2
	}
	return 0
}
