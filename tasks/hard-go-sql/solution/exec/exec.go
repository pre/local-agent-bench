package exec

import (
	"math/big"
	"slices"
	"strings"

	"example.com/minisql/plan"
	"example.com/minisql/sql"
	"example.com/minisql/value"
)

// Result is the result of a query.
type Result struct {
	Columns []string
	Rows    [][]value.Value
}

type outRow struct {
	out  []value.Value
	keys []value.Value
}

// Run runs the query: WHERE, grouping, HAVING, the output columns, DISTINCT,
// ORDER BY, OFFSET and LIMIT.
func Run(q *plan.Query) (*Result, error) {
	res := &Result{}
	for _, o := range q.Outputs {
		res.Columns = append(res.Columns, o.Name)
	}
	var inputs [][]value.Value
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
		inputs = append(inputs, in)
	}
	if q.Grouped {
		var err error
		if inputs, err = group(q, inputs); err != nil {
			return nil, err
		}
	}

	var rows []outRow
	seen := map[string]bool{}
	for _, in := range inputs {
		if q.Having != nil {
			h, err := Eval(q.Having, in)
			if err != nil {
				return nil, err
			}
			if h.IsNull() || !h.Bool() {
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
		if q.Distinct {
			k := rowKey(out)
			if seen[k] {
				continue
			}
			seen[k] = true
		}
		keys := make([]value.Value, len(q.Order))
		for i, o := range q.Order {
			if o.Output >= 0 {
				keys[i] = out[o.Output]
				continue
			}
			v, err := Eval(o.Expr, in)
			if err != nil {
				return nil, err
			}
			keys[i] = v
		}
		rows = append(rows, outRow{out, keys})
	}
	if len(q.Order) > 0 {
		slices.SortStableFunc(rows, func(a, b outRow) int {
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

func rowKey(vals []value.Value) string {
	var b strings.Builder
	for _, v := range vals {
		b.WriteString(v.Key())
		b.WriteByte(0)
	}
	return b.String()
}

// group puts the input rows in groups and gives one group row for each
// group: the group values, then the results of the aggregate functions.
func group(q *plan.Query, inputs [][]value.Value) ([][]value.Value, error) {
	type grp struct {
		keys []value.Value
		aggs []*aggState
	}
	var groups []*grp
	index := map[string]*grp{}
	newGroup := func(keys []value.Value) *grp {
		g := &grp{keys: keys}
		for _, a := range q.Aggs {
			g.aggs = append(g.aggs, newAggState(a))
		}
		groups = append(groups, g)
		return g
	}
	if len(q.GroupBy) == 0 {
		newGroup(nil)
	}
	for _, in := range inputs {
		var g *grp
		if len(q.GroupBy) == 0 {
			g = groups[0]
		} else {
			keys := make([]value.Value, len(q.GroupBy))
			for i, e := range q.GroupBy {
				v, err := Eval(e, in)
				if err != nil {
					return nil, err
				}
				keys[i] = v
			}
			k := rowKey(keys)
			if g = index[k]; g == nil {
				g = newGroup(keys)
				index[k] = g
			}
		}
		for _, a := range g.aggs {
			if err := a.add(in); err != nil {
				return nil, err
			}
		}
	}
	out := make([][]value.Value, 0, len(groups))
	for _, g := range groups {
		row := slices.Clone(g.keys)
		for _, a := range g.aggs {
			v, err := a.result()
			if err != nil {
				return nil, err
			}
			row = append(row, v)
		}
		out = append(out, row)
	}
	return out, nil
}

type aggState struct {
	agg   *plan.Agg
	count int64
	isum  big.Int
	fsum  float64
	best  value.Value
	seen  map[string]bool
}

func newAggState(a *plan.Agg) *aggState {
	s := &aggState{agg: a}
	if a.Distinct {
		s.seen = map[string]bool{}
	}
	return s
}

func (s *aggState) add(row []value.Value) error {
	if s.agg.Arg == nil {
		s.count++
		return nil
	}
	v, err := Eval(s.agg.Arg, row)
	if err != nil || v.IsNull() {
		return err
	}
	if s.seen != nil {
		k := v.Key()
		if s.seen[k] {
			return nil
		}
		s.seen[k] = true
	}
	s.count++
	switch s.agg.Name {
	case "SUM", "AVG":
		if v.Type() == value.Int {
			s.isum.Add(&s.isum, big.NewInt(v.Int()))
		} else {
			s.fsum += v.Float()
		}
	case "MIN":
		if s.count == 1 || value.Compare(v, s.best) < 0 {
			s.best = v
		}
	case "MAX":
		if s.count == 1 || value.Compare(v, s.best) > 0 {
			s.best = v
		}
	}
	return nil
}

func (s *aggState) result() (value.Value, error) {
	if s.agg.Name == "COUNT" {
		return value.NewInt(s.count), nil
	}
	if s.count == 0 {
		return value.NullValue, nil
	}
	intArg := s.agg.Arg.Type() == value.Int
	switch s.agg.Name {
	case "SUM":
		if !intArg {
			return value.NewFloat(s.fsum), nil
		}
		if !s.isum.IsInt64() {
			return value.NullValue, sql.Errorf("overflow", "SUM does not fit in INT")
		}
		return value.NewInt(s.isum.Int64()), nil
	case "AVG":
		if !intArg {
			return value.NewFloat(s.fsum / float64(s.count)), nil
		}
		f, _ := new(big.Rat).SetFrac(&s.isum, big.NewInt(s.count)).Float64()
		return value.NewFloat(f), nil
	}
	return s.best, nil
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
