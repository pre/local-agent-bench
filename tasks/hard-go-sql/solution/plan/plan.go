package plan

import (
	"strings"

	"example.com/minisql/sql"
	"example.com/minisql/table"
	"example.com/minisql/value"
)

// Output is one column of the result.
type Output struct {
	Name string
	Expr Expr
}

// Order is one sort key. Output is the number of the output column (from 0)
// when the key is an output column, else -1 and Expr is the key.
type Order struct {
	Expr   Expr
	Output int
	Desc   bool
}

// Agg is an aggregate function. Arg is nil for COUNT(*).
type Agg struct {
	Name     string
	Arg      Expr
	Distinct bool
	T        value.Type
}

// Query is a checked query.
//
// In an aggregate query (Grouped), GroupBy and the arguments of Aggs read
// the input rows. Having, Outputs and Order read group rows: the values of
// the GroupBy expressions, then the values of Aggs.
type Query struct {
	Table    *table.Table
	Where    Expr // nil: all rows
	Grouped  bool
	GroupBy  []Expr
	Aggs     []*Agg
	Having   Expr // nil: all groups
	Distinct bool
	Outputs  []Output
	Order    []Order
	Limit    int64 // -1: no limit
	Offset   int64
}

// Build checks the statement and makes its plan.
func Build(s *sql.Select, tables map[string]*table.Table) (*Query, error) {
	t, ok := tables[strings.ToLower(s.From)]
	if !ok {
		return nil, sql.Errorf("unknown_table", "no table %q", s.From)
	}
	b := &binder{table: t}
	q := &Query{Table: t, Limit: s.Limit, Offset: s.Offset, Distinct: s.Distinct}

	if s.Where != nil {
		w, err := b.bindIn(s.Where, "WHERE")
		if err != nil {
			return nil, err
		}
		if err := needBool(w, "WHERE"); err != nil {
			return nil, err
		}
		q.Where = w
	}

	// Expand "*" into the columns of the table.
	var items []sql.SelectItem
	for _, it := range s.Items {
		if !it.Star {
			items = append(items, it)
			continue
		}
		for _, c := range t.Columns {
			items = append(items, sql.SelectItem{Expr: &sql.ColumnRef{Name: c.Name}})
		}
	}

	q.Grouped = len(s.GroupBy) > 0 || s.Having != nil
	for _, it := range items {
		q.Grouped = q.Grouped || hasAggregate(it.Expr)
	}
	for _, o := range s.OrderBy {
		q.Grouped = q.Grouped || hasAggregate(o.Expr)
	}

	bindOut := b.bind
	var g *groupBinder
	if q.Grouped {
		g = &groupBinder{b: b}
		for _, ge := range s.GroupBy {
			e, err := resolveGroupItem(ge, items, t)
			if err != nil {
				return nil, err
			}
			bound, err := b.bindIn(e, "GROUP BY")
			if err != nil {
				return nil, err
			}
			g.keys = append(g.keys, canon(e))
			g.types = append(g.types, bound.Type())
			q.GroupBy = append(q.GroupBy, bound)
		}
		bindOut = g.bind
		if s.Having != nil {
			h, err := g.bind(s.Having)
			if err != nil {
				return nil, err
			}
			if err := needBool(h, "HAVING"); err != nil {
				return nil, err
			}
			q.Having = h
		}
	}

	for _, it := range items {
		e, err := bindOut(it.Expr)
		if err != nil {
			return nil, err
		}
		q.Outputs = append(q.Outputs, Output{Name: outputName(it, t), Expr: e})
	}

	for _, o := range s.OrderBy {
		ord, err := bindOrder(o, items, q.Outputs, bindOut, s.Distinct)
		if err != nil {
			return nil, err
		}
		q.Order = append(q.Order, ord)
	}
	if g != nil {
		q.Aggs = g.aggs
	}
	return q, nil
}

func needBool(e Expr, where string) error {
	if e.Type() != value.Bool && e.Type() != value.Null {
		return sql.Errorf("type", "%s needs a BOOL, not %v", where, e.Type())
	}
	return nil
}

func orderable(t value.Type) bool {
	return t == value.Null || t == value.Int || t == value.Float || t == value.Text || t == value.Bool
}

// outputName is the alias, the declared name of a plain column, or the
// canonical text of the expression.
func outputName(item sql.SelectItem, t *table.Table) string {
	if item.Alias != "" {
		return item.Alias
	}
	if ref, ok := item.Expr.(*sql.ColumnRef); ok {
		if i := t.Index(ref.Name); i >= 0 {
			return t.Columns[i].Name
		}
	}
	return item.Expr.String()
}

// resolveGroupItem applies G4: a number or an alias gives the expression of
// a select item. A table column wins over an alias.
func resolveGroupItem(e sql.Expr, items []sql.SelectItem, t *table.Table) (sql.Expr, error) {
	if lit, ok := e.(*sql.Literal); ok && lit.Value.Type() == value.Int {
		n := lit.Value.Int()
		if n < 1 || n > int64(len(items)) {
			return nil, sql.Errorf("ordinal", "GROUP BY %d: the query has %d select items", n, len(items))
		}
		return items[n-1].Expr, nil
	}
	if ref, ok := e.(*sql.ColumnRef); ok && t.Index(ref.Name) < 0 {
		for _, it := range items {
			if it.Alias != "" && strings.EqualFold(it.Alias, ref.Name) {
				return it.Expr, nil
			}
		}
	}
	return e, nil
}

// bindOrder resolves an ORDER BY item: a number, an alias, an expression
// with the canonical text of a select item, or another expression.
func bindOrder(o sql.OrderItem, items []sql.SelectItem, outputs []Output, bind func(sql.Expr) (Expr, error), distinct bool) (Order, error) {
	out := -1
	if lit, ok := o.Expr.(*sql.Literal); ok && lit.Value.Type() == value.Int {
		n := lit.Value.Int()
		if n < 1 || n > int64(len(outputs)) {
			return Order{}, sql.Errorf("ordinal", "ORDER BY %d: the query has %d output columns", n, len(outputs))
		}
		out = int(n - 1)
	}
	if ref, ok := o.Expr.(*sql.ColumnRef); ok && out < 0 {
		for i, it := range items {
			if it.Alias != "" && strings.EqualFold(it.Alias, ref.Name) {
				out = i
				break
			}
		}
	}
	if out < 0 {
		key := canon(o.Expr)
		for i, it := range items {
			if canon(it.Expr) == key {
				out = i
				break
			}
		}
	}
	if out >= 0 {
		e := outputs[out].Expr
		if !orderable(e.Type()) {
			return Order{}, sql.Errorf("type", "cannot sort by %v", e.Type())
		}
		return Order{Expr: e, Output: out, Desc: o.Desc}, nil
	}
	if distinct {
		return Order{}, sql.Errorf("distinct", "ORDER BY %s: with DISTINCT, ORDER BY must use output columns", o.Expr)
	}
	e, err := bind(o.Expr)
	if err != nil {
		return Order{}, err
	}
	if !orderable(e.Type()) {
		return Order{}, sql.Errorf("type", "cannot sort by %v", e.Type())
	}
	return Order{Expr: e, Output: -1, Desc: o.Desc}, nil
}
