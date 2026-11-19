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

// Order is one sort key.
type Order struct {
	Expr Expr
	Desc bool
}

// Query is a checked query.
type Query struct {
	Table   *table.Table
	Where   Expr // nil: all rows
	Outputs []Output
	Order   []Order
	Limit   int64 // -1: no limit
	Offset  int64
}

// Build checks the statement and makes its plan.
func Build(s *sql.Select, tables map[string]*table.Table) (*Query, error) {
	t, ok := tables[strings.ToLower(s.From)]
	if !ok {
		return nil, sql.Errorf("unknown_table", "no table %q", s.From)
	}
	b := &binder{table: t}
	q := &Query{Table: t, Limit: s.Limit, Offset: s.Offset}

	if s.Where != nil {
		w, err := b.bind(s.Where)
		if err != nil {
			return nil, err
		}
		if w.Type() != value.Bool && w.Type() != value.Null {
			return nil, sql.Errorf("type", "WHERE needs a BOOL, not %v", w.Type())
		}
		q.Where = w
	}

	for _, item := range s.Items {
		if item.Star {
			for i, c := range t.Columns {
				q.Outputs = append(q.Outputs, Output{Name: c.Name, Expr: &Col{Index: i, Name: c.Name, T: c.Type}})
			}
			continue
		}
		e, err := b.bind(item.Expr)
		if err != nil {
			return nil, err
		}
		q.Outputs = append(q.Outputs, Output{Name: outputName(item, e), Expr: e})
	}

	for _, o := range s.OrderBy {
		e, err := b.bindOrder(o.Expr, q.Outputs, s.Items)
		if err != nil {
			return nil, err
		}
		if e.Type() != value.Null && !orderable(e.Type()) {
			return nil, sql.Errorf("type", "cannot sort by %v", e.Type())
		}
		q.Order = append(q.Order, Order{Expr: e, Desc: o.Desc})
	}
	return q, nil
}

func orderable(t value.Type) bool {
	return t == value.Int || t == value.Float || t == value.Text || t == value.Bool
}

// outputName is the alias, the declared name of a plain column, or the
// canonical text of the expression.
func outputName(item sql.SelectItem, e Expr) string {
	if item.Alias != "" {
		return item.Alias
	}
	if c, ok := e.(*Col); ok {
		if _, plain := item.Expr.(*sql.ColumnRef); plain {
			return c.Name
		}
	}
	return item.Expr.String()
}

// bindOrder resolves an ORDER BY expression: an INT literal is the number of
// an output column (from 1), a plain name that is the alias of an output
// column is that column, and other expressions use the columns of the table.
func (b *binder) bindOrder(e sql.Expr, outputs []Output, items []sql.SelectItem) (Expr, error) {
	if lit, ok := e.(*sql.Literal); ok && lit.Value.Type() == value.Int {
		n := lit.Value.Int()
		if n < 1 || n > int64(len(outputs)) {
			return nil, sql.Errorf("ordinal", "ORDER BY %d: the query has %d output columns", n, len(outputs))
		}
		return outputs[n-1].Expr, nil
	}
	if ref, ok := e.(*sql.ColumnRef); ok {
		for _, o := range outputs {
			if strings.EqualFold(o.Name, ref.Name) && aliasOf(items, ref.Name) {
				return o.Expr, nil
			}
		}
	}
	return b.bind(e)
}

func aliasOf(items []sql.SelectItem, name string) bool {
	for _, it := range items {
		if it.Alias != "" && strings.EqualFold(it.Alias, name) {
			return true
		}
	}
	return false
}
