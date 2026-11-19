package plan

import (
	"strings"

	"example.com/minisql/sql"
	"example.com/minisql/value"
)

func hasAggregate(e sql.Expr) bool {
	found := false
	sql.Walk(e, func(n sql.Expr) {
		if c, ok := n.(*sql.Call); ok && Aggregates[c.Name] {
			found = true
		}
	})
	return found
}

// canon is the canonical text of an expression, with column names in lower
// case.
func canon(e sql.Expr) string {
	return lowerNames(e).String()
}

func lowerNames(e sql.Expr) sql.Expr {
	switch n := e.(type) {
	case *sql.ColumnRef:
		return &sql.ColumnRef{Name: strings.ToLower(n.Name)}
	case *sql.Unary:
		return &sql.Unary{Op: n.Op, X: lowerNames(n.X)}
	case *sql.Binary:
		return &sql.Binary{Op: n.Op, L: lowerNames(n.L), R: lowerNames(n.R)}
	case *sql.IsNull:
		return &sql.IsNull{X: lowerNames(n.X), Not: n.Not}
	case *sql.Call:
		c := &sql.Call{Name: n.Name, Star: n.Star, Distinct: n.Distinct}
		for _, a := range n.Args {
			c.Args = append(c.Args, lowerNames(a))
		}
		return c
	}
	return e
}

// groupBinder binds the expressions that are computed for each group (G5).
type groupBinder struct {
	b       *binder
	keys    []string // canonical texts of the GROUP BY expressions
	types   []value.Type
	aggs    []*Agg
	aggKeys map[string]int
}

func (g *groupBinder) bind(e sql.Expr) (Expr, error) {
	key := canon(e)
	for i, k := range g.keys {
		if k == key {
			return &Col{Index: i, Name: e.String(), T: g.types[i]}, nil
		}
	}
	switch n := e.(type) {
	case *sql.Literal:
		return &Const{V: n.Value}, nil
	case *sql.ColumnRef:
		if g.b.table.Index(n.Name) >= 0 {
			return nil, sql.Errorf("grouping", "column %s must be in GROUP BY or in an aggregate function", n.Name)
		}
		return nil, sql.Errorf("unknown_column", "no column %q in table %s", n.Name, g.b.table.Name)
	case *sql.Unary:
		x, err := g.bind(n.X)
		if err != nil {
			return nil, err
		}
		return unary(n.Op, x)
	case *sql.Binary:
		l, err := g.bind(n.L)
		if err != nil {
			return nil, err
		}
		r, err := g.bind(n.R)
		if err != nil {
			return nil, err
		}
		return binary(n.Op, l, r)
	case *sql.IsNull:
		x, err := g.bind(n.X)
		if err != nil {
			return nil, err
		}
		return &IsNull{X: x, Not: n.Not}, nil
	case *sql.Call:
		if Aggregates[n.Name] {
			return g.aggregate(n, key)
		}
		if n.Star || n.Distinct {
			return nil, sql.Errorf("syntax", "%s is not valid", n)
		}
		args := make([]Expr, len(n.Args))
		for i, a := range n.Args {
			x, err := g.bind(a)
			if err != nil {
				return nil, err
			}
			args[i] = x
		}
		return scalarFunc(n.Name, args)
	}
	return nil, sql.Errorf("syntax", "unknown expression %T", e)
}

func (g *groupBinder) aggregate(c *sql.Call, key string) (Expr, error) {
	if g.aggKeys == nil {
		g.aggKeys = map[string]int{}
	}
	if i, ok := g.aggKeys[key]; ok {
		return &Col{Index: len(g.keys) + i, Name: c.String(), T: g.aggs[i].T}, nil
	}
	agg := &Agg{Name: c.Name, Distinct: c.Distinct}
	switch {
	case c.Star:
		if c.Name != "COUNT" {
			return nil, sql.Errorf("syntax", "%s(*) is not valid", c.Name)
		}
		agg.T = value.Int
	case len(c.Args) != 1:
		return nil, sql.Errorf("type", "%s needs one argument", c.Name)
	default:
		for _, a := range c.Args {
			if hasAggregate(a) {
				return nil, sql.Errorf("aggregate", "%s: an aggregate function inside an aggregate function", c)
			}
		}
		arg, err := g.b.bind(c.Args[0])
		if err != nil {
			return nil, err
		}
		agg.Arg = arg
		t := arg.Type()
		switch c.Name {
		case "COUNT":
			agg.T = value.Int
		case "SUM", "AVG":
			if t != value.Null && !t.Numeric() {
				return nil, sql.Errorf("type", "%s needs a number, not %v", c.Name, t)
			}
			agg.T = t
			if t == value.Null {
				agg.T = value.Int
			}
			if c.Name == "AVG" {
				agg.T = value.Float
			}
		default:
			if t == value.Null {
				return nil, sql.Errorf("type", "%s needs a typed argument, not NULL", c.Name)
			}
			agg.T = t
		}
	}
	g.aggKeys[key] = len(g.aggs)
	g.aggs = append(g.aggs, agg)
	return &Col{Index: len(g.keys) + len(g.aggs) - 1, Name: c.String(), T: agg.T}, nil
}
