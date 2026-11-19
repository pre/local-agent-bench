// Package exec runs a checked query.
package exec

import (
	"math"
	"strings"
	"unicode/utf8"

	"example.com/minisql/plan"
	"example.com/minisql/sql"
	"example.com/minisql/value"
)

// Eval computes an expression for one input row.
func Eval(e plan.Expr, row []value.Value) (value.Value, error) {
	switch n := e.(type) {
	case *plan.Const:
		return n.V, nil
	case *plan.Col:
		return row[n.Index], nil
	case *plan.IsNull:
		x, err := Eval(n.X, row)
		if err != nil {
			return value.NullValue, err
		}
		return value.NewBool(x.IsNull() != n.Not), nil
	case *plan.Unary:
		x, err := Eval(n.X, row)
		if err != nil || x.IsNull() {
			return value.NullValue, err
		}
		if n.Op == "NOT" {
			return value.NewBool(!x.Bool()), nil
		}
		if x.Type() == value.Float {
			return value.NewFloat(-x.Float()), nil
		}
		if x.Int() == math.MinInt64 {
			return value.NullValue, sql.Errorf("overflow", "-(%d) does not fit in INT", x.Int())
		}
		return value.NewInt(-x.Int()), nil
	case *plan.Binary:
		return evalBinary(n, row)
	case *plan.Func:
		return evalFunc(n, row)
	}
	return value.NullValue, sql.Errorf("syntax", "unknown expression %T", e)
}

func evalBinary(n *plan.Binary, row []value.Value) (value.Value, error) {
	l, err := Eval(n.L, row)
	if err != nil {
		return value.NullValue, err
	}
	r, err := Eval(n.R, row)
	if err != nil {
		return value.NullValue, err
	}
	switch n.Op {
	case "AND":
		// Three-valued logic: FALSE wins over NULL.
		if !l.IsNull() && !l.Bool() || !r.IsNull() && !r.Bool() {
			return value.NewBool(false), nil
		}
		if l.IsNull() || r.IsNull() {
			return value.NullValue, nil
		}
		return value.NewBool(true), nil
	case "OR":
		if !l.IsNull() && l.Bool() || !r.IsNull() && r.Bool() {
			return value.NewBool(true), nil
		}
		if l.IsNull() || r.IsNull() {
			return value.NullValue, nil
		}
		return value.NewBool(false), nil
	}
	if l.IsNull() || r.IsNull() {
		return value.NullValue, nil
	}
	switch n.Op {
	case "=", "<>", "<", "<=", ">", ">=":
		c := value.Compare(l, r)
		var b bool
		switch n.Op {
		case "=":
			b = c == 0
		case "<>":
			b = c != 0
		case "<":
			b = c < 0
		case "<=":
			b = c <= 0
		case ">":
			b = c > 0
		default:
			b = c >= 0
		}
		return value.NewBool(b), nil
	case "||":
		return value.NewText(l.Text() + r.Text()), nil
	}
	if n.T == value.Float {
		return floatOp(n.Op, l.AsFloat(), r.AsFloat())
	}
	return IntOp(n.Op, l.Int(), r.Int())
}

func floatOp(op string, a, b float64) (value.Value, error) {
	var f float64
	switch op {
	case "+":
		f = a + b
	case "-":
		f = a - b
	case "*":
		f = a * b
	case "/":
		if b == 0 {
			return value.NullValue, sql.Errorf("division_by_zero", "division by zero")
		}
		f = a / b
	}
	if math.IsInf(f, 0) || math.IsNaN(f) {
		return value.NullValue, sql.Errorf("overflow", "the result of %s is not a finite FLOAT", op)
	}
	return value.NewFloat(f), nil
}

// IntOp computes an INT operation. An overflow is an error.
func IntOp(op string, a, b int64) (value.Value, error) {
	overflow := func() (value.Value, error) {
		return value.NullValue, sql.Errorf("overflow", "%d %s %d does not fit in INT", a, op, b)
	}
	switch op {
	case "+":
		s := a + b
		if (s > a) != (b > 0) {
			return overflow()
		}
		return value.NewInt(s), nil
	case "-":
		s := a - b
		if (s < a) != (b > 0) {
			return overflow()
		}
		return value.NewInt(s), nil
	case "*":
		if a == 0 || b == 0 {
			return value.NewInt(0), nil
		}
		p := a * b
		if p/b != a || (a == -1 && b == math.MinInt64) || (b == -1 && a == math.MinInt64) {
			return overflow()
		}
		return value.NewInt(p), nil
	case "/", "%":
		if b == 0 {
			return value.NullValue, sql.Errorf("division_by_zero", "division by zero")
		}
		if a == math.MinInt64 && b == -1 {
			if op == "%" {
				return value.NewInt(0), nil
			}
			return overflow()
		}
		if op == "/" {
			return value.NewInt(a / b), nil
		}
		return value.NewInt(a % b), nil
	}
	return value.NullValue, sql.Errorf("syntax", "unknown operator %s", op)
}

func evalFunc(n *plan.Func, row []value.Value) (value.Value, error) {
	args := make([]value.Value, len(n.Args))
	for i, a := range n.Args {
		v, err := Eval(a, row)
		if err != nil {
			return value.NullValue, err
		}
		args[i] = v
	}
	if n.Name == "COALESCE" {
		for _, a := range args {
			if !a.IsNull() {
				if n.T == value.Float {
					return value.NewFloat(a.AsFloat()), nil
				}
				return a, nil
			}
		}
		return value.NullValue, nil
	}
	if args[0].IsNull() {
		return value.NullValue, nil
	}
	switch n.Name {
	case "LOWER":
		return value.NewText(strings.ToLower(args[0].Text())), nil
	case "UPPER":
		return value.NewText(strings.ToUpper(args[0].Text())), nil
	case "LENGTH":
		return value.NewInt(int64(utf8.RuneCountInString(args[0].Text()))), nil
	case "ABS":
		if args[0].Type() == value.Float {
			return value.NewFloat(math.Abs(args[0].Float())), nil
		}
		if args[0].Int() == math.MinInt64 {
			return value.NullValue, sql.Errorf("overflow", "ABS(%d) does not fit in INT", args[0].Int())
		}
		if args[0].Int() < 0 {
			return value.NewInt(-args[0].Int()), nil
		}
		return args[0], nil
	case "ROUND":
		digits := int64(0)
		if len(args) == 2 {
			if args[1].IsNull() {
				return value.NullValue, nil
			}
			digits = args[1].Int()
		}
		scale := math.Pow(10, float64(digits))
		return value.NewFloat(math.Round(args[0].AsFloat()*scale) / scale), nil
	}
	return value.NullValue, sql.Errorf("unknown_function", "no function %s", n.Name)
}
