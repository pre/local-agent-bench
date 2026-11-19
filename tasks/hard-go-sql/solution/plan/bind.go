package plan

import (
	"example.com/minisql/sql"
	"example.com/minisql/table"
	"example.com/minisql/value"
)

// Aggregates are the names of the aggregate functions of docs/SQL.md.
var Aggregates = map[string]bool{"COUNT": true, "SUM": true, "MIN": true, "MAX": true, "AVG": true}

type binder struct {
	table *table.Table
}

// bindIn is bind for WHERE and GROUP BY, where aggregate functions are not
// permitted.
func (b *binder) bindIn(e sql.Expr, where string) (Expr, error) {
	if hasAggregate(e) {
		return nil, sql.Errorf("aggregate", "aggregate function in %s", where)
	}
	return b.bind(e)
}

// bind checks an expression against the columns of the table.
func (b *binder) bind(e sql.Expr) (Expr, error) {
	switch n := e.(type) {
	case *sql.Literal:
		return &Const{V: n.Value}, nil
	case *sql.ColumnRef:
		i := b.table.Index(n.Name)
		if i < 0 {
			return nil, sql.Errorf("unknown_column", "no column %q in table %s", n.Name, b.table.Name)
		}
		c := b.table.Columns[i]
		return &Col{Index: i, Name: c.Name, T: c.Type}, nil
	case *sql.Unary:
		x, err := b.bind(n.X)
		if err != nil {
			return nil, err
		}
		return unary(n.Op, x)
	case *sql.Binary:
		l, err := b.bind(n.L)
		if err != nil {
			return nil, err
		}
		r, err := b.bind(n.R)
		if err != nil {
			return nil, err
		}
		return binary(n.Op, l, r)
	case *sql.IsNull:
		x, err := b.bind(n.X)
		if err != nil {
			return nil, err
		}
		return &IsNull{X: x, Not: n.Not}, nil
	case *sql.Call:
		if Aggregates[n.Name] {
			return nil, sql.Errorf("aggregate", "aggregate function %s is not permitted here", n.Name)
		}
		if n.Star {
			return nil, sql.Errorf("syntax", "%s(*) is not valid", n.Name)
		}
		args := make([]Expr, len(n.Args))
		for i, a := range n.Args {
			x, err := b.bind(a)
			if err != nil {
				return nil, err
			}
			args[i] = x
		}
		return scalarFunc(n.Name, args)
	}
	return nil, sql.Errorf("syntax", "unknown expression %T", e)
}

func unary(op string, x Expr) (Expr, error) {
	t := x.Type()
	switch op {
	case "NOT":
		if t != value.Bool && t != value.Null {
			return nil, sql.Errorf("type", "NOT needs a BOOL, not %v", t)
		}
		return &Unary{Op: op, X: x, T: value.Bool}, nil
	case "-":
		if t == value.Null {
			t = value.Int
		}
		if !t.Numeric() {
			return nil, sql.Errorf("type", "unary - needs a number, not %v", t)
		}
		return &Unary{Op: op, X: x, T: t}, nil
	}
	return nil, sql.Errorf("syntax", "unknown operator %s", op)
}

// NumericResult is the type of an arithmetic operation: INT if both operands
// are INT (or NULL), else FLOAT.
func NumericResult(l, r value.Type) value.Type {
	if l == value.Float || r == value.Float {
		return value.Float
	}
	return value.Int
}

// Comparable tells if two types can be compared.
func Comparable(l, r value.Type) bool {
	if l == value.Null || r == value.Null {
		return true
	}
	if l.Numeric() && r.Numeric() {
		return true
	}
	return l == r
}

func binary(op string, l, r Expr) (Expr, error) {
	lt, rt := l.Type(), r.Type()
	switch op {
	case "AND", "OR":
		for _, t := range []value.Type{lt, rt} {
			if t != value.Bool && t != value.Null {
				return nil, sql.Errorf("type", "%s needs BOOL operands, not %v", op, t)
			}
		}
		return &Binary{Op: op, L: l, R: r, T: value.Bool}, nil
	case "=", "<>", "<", "<=", ">", ">=":
		if !Comparable(lt, rt) {
			return nil, sql.Errorf("type", "cannot compare %v and %v", lt, rt)
		}
		return &Binary{Op: op, L: l, R: r, T: value.Bool}, nil
	case "||":
		for _, t := range []value.Type{lt, rt} {
			if t != value.Text && t != value.Null {
				return nil, sql.Errorf("type", "|| needs TEXT operands, not %v", t)
			}
		}
		return &Binary{Op: op, L: l, R: r, T: value.Text}, nil
	case "+", "-", "*", "/", "%":
		for _, t := range []value.Type{lt, rt} {
			if !t.Numeric() && t != value.Null {
				return nil, sql.Errorf("type", "%s needs numbers, not %v", op, t)
			}
		}
		t := NumericResult(lt, rt)
		if op == "%" && t != value.Int {
			return nil, sql.Errorf("type", "%% needs INT operands")
		}
		return &Binary{Op: op, L: l, R: r, T: t}, nil
	}
	return nil, sql.Errorf("syntax", "unknown operator %s", op)
}

func scalarFunc(name string, args []Expr) (Expr, error) {
	argc := func(min, max int) error {
		if len(args) < min || len(args) > max {
			return sql.Errorf("type", "%s: wrong number of arguments", name)
		}
		return nil
	}
	is := func(i int, ok func(value.Type) bool, what string) error {
		if t := args[i].Type(); t != value.Null && !ok(t) {
			return sql.Errorf("type", "%s: argument %d must be %s, not %v", name, i+1, what, t)
		}
		return nil
	}
	isText := func(t value.Type) bool { return t == value.Text }
	isNum := func(t value.Type) bool { return t.Numeric() }
	isInt := func(t value.Type) bool { return t == value.Int }
	switch name {
	case "LOWER", "UPPER":
		if err := argc(1, 1); err != nil {
			return nil, err
		}
		if err := is(0, isText, "TEXT"); err != nil {
			return nil, err
		}
		return &Func{Name: name, Args: args, T: value.Text}, nil
	case "LENGTH":
		if err := argc(1, 1); err != nil {
			return nil, err
		}
		if err := is(0, isText, "TEXT"); err != nil {
			return nil, err
		}
		return &Func{Name: name, Args: args, T: value.Int}, nil
	case "ABS":
		if err := argc(1, 1); err != nil {
			return nil, err
		}
		if err := is(0, isNum, "a number"); err != nil {
			return nil, err
		}
		t := args[0].Type()
		if t == value.Null {
			t = value.Int
		}
		return &Func{Name: name, Args: args, T: t}, nil
	case "ROUND":
		if err := argc(1, 2); err != nil {
			return nil, err
		}
		if err := is(0, isNum, "a number"); err != nil {
			return nil, err
		}
		if len(args) == 2 {
			if err := is(1, isInt, "INT"); err != nil {
				return nil, err
			}
		}
		return &Func{Name: name, Args: args, T: value.Float}, nil
	case "COALESCE":
		if err := argc(1, 1000); err != nil {
			return nil, err
		}
		t := value.Null
		for _, a := range args {
			at := a.Type()
			switch {
			case at == value.Null:
			case t == value.Null:
				t = at
			case t.Numeric() && at.Numeric():
				t = NumericResult(t, at)
			case t != at:
				return nil, sql.Errorf("type", "COALESCE: arguments of types %v and %v", t, at)
			}
		}
		return &Func{Name: name, Args: args, T: t}, nil
	}
	return nil, sql.Errorf("unknown_function", "no function %s", name)
}
