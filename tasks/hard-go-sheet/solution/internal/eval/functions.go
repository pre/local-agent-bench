package eval

import (
	"math"

	"example.com/sheet/internal/addr"
	"example.com/sheet/internal/formula"
	"example.com/sheet/value"
)

// Builtins are the names of the built-in functions. A custom function cannot
// have one of these names.
var Builtins = map[string]bool{
	"IF": true, "AND": true, "OR": true, "NOT": true,
	"SUM": true, "MIN": true, "MAX": true, "AVERAGE": true, "COUNT": true,
	"ABS": true, "ROUND": true,
}

func evalCall(n *formula.Call, env *Env) value.Value {
	switch n.Name {
	case "IF":
		return evalIf(n, env)
	case "SUM", "MIN", "MAX", "AVERAGE", "COUNT":
		return aggregate(n, env)
	}
	args := evalArgs(n.Args, env)
	if f, ok := env.Funcs[n.Name]; ok {
		return f(args)
	}
	for _, a := range args {
		if a.IsError() {
			return a
		}
	}
	switch n.Name {
	case "AND", "OR":
		if len(args) == 0 {
			return value.Error(value.ErrValue)
		}
		result := n.Name == "AND"
		for _, a := range args {
			b, errv := toBool(a)
			if errv != nil {
				return *errv
			}
			if n.Name == "AND" {
				result = result && b
			} else {
				result = result || b
			}
		}
		return value.Boolean(result)
	case "NOT":
		if len(args) != 1 {
			return value.Error(value.ErrValue)
		}
		b, errv := toBool(args[0])
		if errv != nil {
			return *errv
		}
		return value.Boolean(!b)
	case "ABS":
		if len(args) != 1 {
			return value.Error(value.ErrValue)
		}
		f, errv := toNumber(args[0])
		if errv != nil {
			return *errv
		}
		return value.Number(math.Abs(f))
	case "ROUND":
		if len(args) != 2 {
			return value.Error(value.ErrValue)
		}
		f, errv := toNumber(args[0])
		if errv != nil {
			return *errv
		}
		d, errv := toNumber(args[1])
		if errv != nil {
			return *errv
		}
		scale := math.Pow(10, math.Trunc(d))
		return value.Number(math.Round(f*scale) / scale)
	}
	return value.Error(value.ErrName)
}

// evalArgs evaluates all arguments from left to right. A range gives the
// values of its cells.
func evalArgs(args []formula.Expr, env *Env) []value.Value {
	var out []value.Value
	for _, a := range args {
		if r, ok := a.(*formula.RangeRef); ok {
			for _, c := range r.Range.Cells() {
				out = append(out, env.Read(c))
			}
			continue
		}
		out = append(out, Eval(a, env))
	}
	return out
}

// evalIf evaluates the condition, then only the selected branch.
func evalIf(n *formula.Call, env *Env) value.Value {
	if len(n.Args) < 2 || len(n.Args) > 3 {
		return value.Error(value.ErrValue)
	}
	if _, ok := n.Args[0].(*formula.RangeRef); ok {
		return value.Error(value.ErrValue)
	}
	cond, errv := toBool(Eval(n.Args[0], env))
	if errv != nil {
		return *errv
	}
	branch := 2
	if cond {
		branch = 1
	}
	if branch >= len(n.Args) {
		return value.Boolean(false)
	}
	if _, ok := n.Args[branch].(*formula.RangeRef); ok {
		return value.Error(value.ErrValue)
	}
	return Eval(n.Args[branch], env)
}

// aggregate computes SUM, MIN, MAX, AVERAGE and COUNT. In a range, only
// numbers count: empty cells, texts and bools are ignored. A direct argument
// is converted with the rules of arithmetic. An error value gives the error.
func aggregate(n *formula.Call, env *Env) value.Value {
	var nums []float64
	for _, a := range n.Args {
		if r, ok := a.(*formula.RangeRef); ok {
			var errv *value.Value
			visit := func(_ addr.Addr, v value.Value) {
				switch {
				case errv != nil:
				case v.Kind() == value.KindError:
					errv = &v
				case v.Kind() == value.KindNumber:
					nums = append(nums, v.Num())
				}
			}
			if env.ReadRange != nil {
				env.ReadRange(r.Range, visit)
			} else {
				for _, c := range r.Range.Cells() {
					visit(c, env.Read(c))
				}
			}
			if errv != nil {
				return *errv
			}
			continue
		}
		f, errv := toNumber(Eval(a, env))
		if errv != nil {
			return *errv
		}
		nums = append(nums, f)
	}
	switch n.Name {
	case "COUNT":
		return value.Number(float64(len(nums)))
	case "AVERAGE":
		if len(nums) == 0 {
			return value.Error(value.ErrDivZero)
		}
		return value.Number(sum(nums) / float64(len(nums)))
	case "MIN", "MAX":
		if len(nums) == 0 {
			return value.Number(0)
		}
		m := nums[0]
		for _, f := range nums[1:] {
			if n.Name == "MIN" {
				m = math.Min(m, f)
			} else {
				m = math.Max(m, f)
			}
		}
		return value.Number(m)
	}
	return value.Number(sum(nums))
}

func sum(nums []float64) float64 {
	s := 0.0
	for _, f := range nums {
		s += f
	}
	return s
}
