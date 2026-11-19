package exec

import (
	"slices"

	"example.com/minisql/plan"
	"example.com/minisql/value"
)

// Result is the result of a query.
type Result struct {
	Columns []string
	Rows    [][]value.Value
}

// Run runs the query: WHERE, the output columns, ORDER BY, OFFSET and LIMIT.
func Run(q *plan.Query) (*Result, error) {
	res := &Result{}
	for _, o := range q.Outputs {
		res.Columns = append(res.Columns, o.Name)
	}
	type sortRow struct {
		out  []value.Value
		keys []value.Value
	}
	var rows []sortRow
	for _, in := range q.Table.Rows {
		if q.Where != nil {
			w, err := Eval(q.Where, in)
			if err != nil {
				return nil, err
			}
			if w.IsNull() || !w.Bool() {
				continue
			}
		}
		out := make([]value.Value, len(q.Outputs))
		for i, o := range q.Outputs {
			v, err := Eval(o.Expr, in)
			if err != nil {
				return nil, err
			}
			out[i] = v
		}
		keys := make([]value.Value, len(q.Order))
		for i, o := range q.Order {
			v, err := Eval(o.Expr, in)
			if err != nil {
				return nil, err
			}
			keys[i] = v
		}
		rows = append(rows, sortRow{out, keys})
	}
	if len(q.Order) > 0 {
		slices.SortStableFunc(rows, func(a, b sortRow) int {
			for i, o := range q.Order {
				c := CompareForSort(a.keys[i], b.keys[i])
				if o.Desc {
					c = -c
				}
				if c != 0 {
					return c
				}
			}
			return 0
		})
	}
	for _, r := range rows {
		res.Rows = append(res.Rows, r.out)
	}
	res.Rows = Window(res.Rows, q.Limit, q.Offset)
	return res, nil
}

// CompareForSort orders values for ORDER BY: NULL is before all other
// values, other values use value.Compare.
func CompareForSort(a, b value.Value) int {
	switch {
	case a.IsNull() && b.IsNull():
		return 0
	case a.IsNull():
		return -1
	case b.IsNull():
		return 1
	}
	return value.Compare(a, b)
}

// Window applies OFFSET and LIMIT (-1: no limit).
func Window(rows [][]value.Value, limit, offset int64) [][]value.Value {
	if offset >= int64(len(rows)) {
		return nil
	}
	rows = rows[offset:]
	if limit >= 0 && limit < int64(len(rows)) {
		rows = rows[:limit]
	}
	return rows
}
