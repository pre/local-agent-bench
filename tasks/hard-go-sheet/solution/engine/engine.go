// Package engine keeps the cells of a sheet and their values up to date.
// docs/ENGINE.md describes the behavior.
package engine

import (
	"errors"
	"fmt"
	"slices"

	"example.com/sheet/internal/addr"
	"example.com/sheet/internal/eval"
	"example.com/sheet/internal/formula"
	"example.com/sheet/value"
)

var (
	// ErrAddress is the error for an invalid cell address.
	ErrAddress = addr.ErrAddress
	// ErrSyntax is the error for a formula that does not parse.
	ErrSyntax = formula.ErrSyntax
	// ErrCycle is the error for a formula that refers to its own cell,
	// directly or through other formulas.
	ErrCycle = errors.New("circular reference")
	// ErrFuncName is the error of RegisterFunc for a name that is not valid.
	ErrFuncName = errors.New("invalid function name")
)

// Func is a custom function (see RegisterFunc).
type Func func(args []value.Value) value.Value

// WatchFunc gets the old and the new value of a watched cell.
type WatchFunc func(cell string, old, new value.Value)

// Edit sets the input of one cell.
type Edit struct {
	Cell  string
	Input string
}

type cell struct {
	input  string
	expr   formula.Expr // nil for a constant
	refs   []addr.Addr  // the single references of the formula text
	ranges []addr.Range // the ranges of the formula text, not expanded
	value  value.Value
	// The reads of the most recent evaluation.
	readCells  []addr.Addr
	readRanges []addr.Range
}

// Sheet is a spreadsheet. The zero value is not usable, use New.
type Sheet struct {
	cells      map[addr.Addr]*cell
	rows       map[int][]int                        // column -> sorted rows of the cells with an input
	dependents map[addr.Addr]map[addr.Addr]struct{} // cell -> formulas with a single reference to it
	rangeUsers map[addr.Addr]struct{}               // formulas that have a range
	watchers   map[addr.Addr][]WatchFunc
	funcs      map[string]eval.Func
}

// New makes an empty sheet.
func New() *Sheet {
	return &Sheet{
		cells:      map[addr.Addr]*cell{},
		rows:       map[int][]int{},
		dependents: map[addr.Addr]map[addr.Addr]struct{}{},
		rangeUsers: map[addr.Addr]struct{}{},
		watchers:   map[addr.Addr][]WatchFunc{},
		funcs:      map[string]eval.Func{},
	}
}

// RegisterFunc adds a custom function that formulas can call. The name must
// be upper case letters and digits, start with a letter, and must not be a
// built-in function, an address or TRUE or FALSE. Register functions before
// the formulas that use them: Set and Apply evaluate formulas immediately,
// and a call of an unknown function gives #NAME?.
func (s *Sheet) RegisterFunc(name string, fn Func) error {
	if !validFuncName(name) {
		return fmt.Errorf("%w: %q", ErrFuncName, name)
	}
	s.funcs[name] = eval.Func(fn)
	return nil
}

func validFuncName(name string) bool {
	if name == "" || name[0] < 'A' || name[0] > 'Z' || eval.Builtins[name] || name == "TRUE" || name == "FALSE" {
		return false
	}
	for i := 0; i < len(name); i++ {
		c := name[i]
		if !(c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_') {
			return false
		}
	}
	_, err := addr.Parse(name)
	return err != nil
}

// Value gives the current value of a cell. An invalid address gives the
// empty value.
func (s *Sheet) Value(name string) value.Value {
	a, err := addr.Parse(name)
	if err != nil {
		return value.Empty
	}
	return s.valueOf(a)
}

// Input gives the input text of a cell, "" for an empty cell.
func (s *Sheet) Input(name string) string {
	a, err := addr.Parse(name)
	if err != nil {
		return ""
	}
	if c, ok := s.cells[a]; ok {
		return c.input
	}
	return ""
}

// Cells gives the addresses of the cells that have an input, by row, then by
// column.
func (s *Sheet) Cells() []string {
	as := make([]addr.Addr, 0, len(s.cells))
	for a := range s.cells {
		as = append(as, a)
	}
	slices.SortFunc(as, addr.Compare)
	out := make([]string, len(as))
	for i, a := range as {
		out[i] = a.String()
	}
	return out
}

// Watch adds a function that the sheet calls when the value of the cell
// changes.
func (s *Sheet) Watch(name string, fn WatchFunc) error {
	a, err := addr.Parse(name)
	if err != nil {
		return err
	}
	s.watchers[a] = append(s.watchers[a], fn)
	return nil
}

// Set sets the input of one cell and updates the sheet. It is Apply with one
// edit.
func (s *Sheet) Set(name, input string) error {
	return s.Apply([]Edit{{Cell: name, Input: input}})
}

type change struct {
	at  addr.Addr
	new *cell // nil clears the cell
	old *cell // nil: the cell was empty
}

// Apply sets the inputs of several cells as one update. A later edit of a
// cell replaces an earlier edit of the same cell. If an edit is not valid,
// or if the new formulas make a cycle, Apply returns an error and the sheet
// does not change.
func (s *Sheet) Apply(edits []Edit) error {
	pos := map[addr.Addr]int{}
	var changes []change
	for i, e := range edits {
		a, err := addr.Parse(e.Cell)
		if err != nil {
			return fmt.Errorf("edit %d: %w", i+1, err)
		}
		c, err := compile(e.Input)
		if err != nil {
			return fmt.Errorf("edit %d: %s: %w", i+1, e.Cell, err)
		}
		if j, ok := pos[a]; ok {
			changes[j].new = c
			continue
		}
		pos[a] = len(changes)
		changes = append(changes, change{at: a, new: c, old: s.cells[a]})
	}

	start := make(map[addr.Addr]value.Value, len(changes))
	for _, ch := range changes {
		start[ch.at] = s.valueOf(ch.at)
	}
	for _, ch := range changes {
		s.define(ch.at, ch.new)
	}
	if bad, ok := s.findCycle(changes); ok {
		for i := len(changes) - 1; i >= 0; i-- {
			s.define(changes[i].at, changes[i].old)
		}
		return fmt.Errorf("%s: %w", bad, ErrCycle)
	}

	affected := s.affected(changes)
	for _, a := range affected {
		if _, ok := start[a]; !ok {
			start[a] = s.valueOf(a)
		}
	}
	changed := make(map[addr.Addr]bool)
	var changedList []addr.Addr
	for _, a := range s.topoOrder(affected) {
		if c, ok := s.cells[a]; ok && c.expr != nil {
			_, edited := pos[a]
			if edited || s.readsChanged(c, changed, changedList) {
				s.evaluate(c)
			}
		}
		if !s.valueOf(a).Equal(start[a]) {
			changed[a] = true
			changedList = append(changedList, a)
		}
	}
	s.notify(changedList, start)
	return nil
}

func (s *Sheet) readsChanged(c *cell, changed map[addr.Addr]bool, changedList []addr.Addr) bool {
	for _, r := range c.readCells {
		if changed[r] {
			return true
		}
	}
	for _, rg := range c.readRanges {
		for _, a := range changedList {
			if rg.Contains(a) {
				return true
			}
		}
	}
	return false
}

// eachDependent calls fn for each formula that refers to the cell a in its
// text: by a single reference or by a range.
func (s *Sheet) eachDependent(a addr.Addr, fn func(d addr.Addr)) {
	for d := range s.dependents[a] {
		fn(d)
	}
	for d := range s.rangeUsers {
		c := s.cells[d]
		for _, rg := range c.ranges {
			if rg.Contains(a) {
				fn(d)
				break
			}
		}
	}
}

// eachInRange calls fn for each cell with an input in the range, by row,
// then by column.
func (s *Sheet) eachInRange(r addr.Range, fn func(a addr.Addr)) {
	if r.From.Col == r.To.Col {
		rows := s.rows[r.From.Col]
		i, _ := slices.BinarySearch(rows, r.From.Row)
		for ; i < len(rows) && rows[i] <= r.To.Row; i++ {
			fn(addr.Addr{Col: r.From.Col, Row: rows[i]})
		}
		return
	}
	var found []addr.Addr
	collect := func(col int, rows []int) {
		i, _ := slices.BinarySearch(rows, r.From.Row)
		for ; i < len(rows) && rows[i] <= r.To.Row; i++ {
			found = append(found, addr.Addr{Col: col, Row: rows[i]})
		}
	}
	if r.To.Col-r.From.Col+1 > len(s.rows) {
		for col, rows := range s.rows {
			if col >= r.From.Col && col <= r.To.Col {
				collect(col, rows)
			}
		}
	} else {
		for col := r.From.Col; col <= r.To.Col; col++ {
			collect(col, s.rows[col])
		}
	}
	slices.SortFunc(found, addr.Compare)
	for _, a := range found {
		fn(a)
	}
}

// findCycle checks the references after the changes. Before the changes
// there was no cycle, so a new cycle goes through a changed formula.
func (s *Sheet) findCycle(changes []change) (addr.Addr, bool) {
	const (
		visiting = 1
		done     = 2
	)
	state := map[addr.Addr]int{}
	var cycle bool
	var visit func(a addr.Addr)
	visit = func(a addr.Addr) {
		state[a] = visiting
		c := s.cells[a]
		next := func(r addr.Addr) {
			if cycle {
				return
			}
			switch state[r] {
			case visiting:
				cycle = true
			case 0:
				if rc, ok := s.cells[r]; ok && rc.expr != nil {
					visit(r)
				} else {
					state[r] = done
				}
			}
		}
		for _, r := range c.refs {
			next(r)
		}
		for _, rg := range c.ranges {
			s.eachInRange(rg, next)
		}
		state[a] = done
	}
	for _, ch := range changes {
		if ch.new != nil && ch.new.expr != nil && state[ch.at] == 0 {
			visit(ch.at)
			if cycle {
				return ch.at, true
			}
		}
	}
	return addr.Addr{}, false
}

// affected gives the changed cells and each formula that refers to them,
// directly or through other formulas.
func (s *Sheet) affected(changes []change) []addr.Addr {
	seen := map[addr.Addr]bool{}
	var queue []addr.Addr
	for _, ch := range changes {
		seen[ch.at] = true
		queue = append(queue, ch.at)
	}
	for i := 0; i < len(queue); i++ {
		s.eachDependent(queue[i], func(d addr.Addr) {
			if !seen[d] {
				seen[d] = true
				queue = append(queue, d)
			}
		})
	}
	return queue
}

// topoOrder sorts the cells so that each formula comes after the cells of
// the set that it refers to.
func (s *Sheet) topoOrder(set []addr.Addr) []addr.Addr {
	in := make(map[addr.Addr]bool, len(set))
	for _, a := range set {
		in[a] = true
	}
	indegree := make(map[addr.Addr]int, len(set))
	for _, a := range set {
		s.eachDependent(a, func(d addr.Addr) {
			if in[d] {
				indegree[d]++
			}
		})
	}
	var ready []addr.Addr
	for _, a := range set {
		if indegree[a] == 0 {
			ready = append(ready, a)
		}
	}
	order := make([]addr.Addr, 0, len(set))
	for len(ready) > 0 {
		a := ready[len(ready)-1]
		ready = ready[:len(ready)-1]
		order = append(order, a)
		s.eachDependent(a, func(d addr.Addr) {
			if in[d] {
				indegree[d]--
				if indegree[d] == 0 {
					ready = append(ready, d)
				}
			}
		})
	}
	return order
}

// notify calls the watchers of the changed cells, by row, then by column.
func (s *Sheet) notify(changed []addr.Addr, start map[addr.Addr]value.Value) {
	var cells []addr.Addr
	for _, a := range changed {
		if len(s.watchers[a]) > 0 {
			cells = append(cells, a)
		}
	}
	slices.SortFunc(cells, addr.Compare)
	for _, a := range cells {
		v := s.valueOf(a)
		for _, fn := range s.watchers[a] {
			fn(a.String(), start[a], v)
		}
	}
}

// compile reads an input. It gives nil for "", which clears the cell.
func compile(input string) (*cell, error) {
	if input == "" {
		return nil, nil
	}
	if input[0] != '=' {
		return &cell{input: input, value: parseConstant(input)}, nil
	}
	expr, err := formula.Parse(input[1:])
	if err != nil {
		return nil, err
	}
	refs, ranges := formula.Deps(expr)
	return &cell{input: input, expr: expr, refs: refs, ranges: ranges}, nil
}

// define replaces the cell at a (nil clears it) and updates the indexes.
func (s *Sheet) define(a addr.Addr, c *cell) {
	if old, ok := s.cells[a]; ok {
		for _, r := range old.refs {
			delete(s.dependents[r], a)
			if len(s.dependents[r]) == 0 {
				delete(s.dependents, r)
			}
		}
		delete(s.rangeUsers, a)
		delete(s.cells, a)
		rows := s.rows[a.Col]
		if i, found := slices.BinarySearch(rows, a.Row); found {
			rows = slices.Delete(rows, i, i+1)
		}
		if len(rows) == 0 {
			delete(s.rows, a.Col)
		} else {
			s.rows[a.Col] = rows
		}
	}
	if c == nil {
		return
	}
	for _, r := range c.refs {
		if s.dependents[r] == nil {
			s.dependents[r] = map[addr.Addr]struct{}{}
		}
		s.dependents[r][a] = struct{}{}
	}
	if len(c.ranges) > 0 {
		s.rangeUsers[a] = struct{}{}
	}
	s.cells[a] = c
	rows := s.rows[a.Col]
	i, _ := slices.BinarySearch(rows, a.Row)
	s.rows[a.Col] = slices.Insert(rows, i, a.Row)
}

// evaluate computes the value of a formula and records the cells and the
// ranges that it reads.
func (s *Sheet) evaluate(c *cell) {
	c.readCells = c.readCells[:0]
	c.readRanges = c.readRanges[:0]
	env := &eval.Env{
		Read: func(a addr.Addr) value.Value {
			c.readCells = append(c.readCells, a)
			return s.valueOf(a)
		},
		ReadRange: func(r addr.Range, visit func(a addr.Addr, v value.Value)) {
			c.readRanges = append(c.readRanges, r)
			s.eachInRange(r, func(a addr.Addr) { visit(a, s.cells[a].value) })
		},
		Funcs: s.funcs,
	}
	c.value = eval.Eval(c.expr, env)
}

func (s *Sheet) valueOf(a addr.Addr) value.Value {
	if c, ok := s.cells[a]; ok {
		return c.value
	}
	return value.Empty
}
