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
	input string
	expr  formula.Expr // nil for a constant
	refs  []addr.Addr  // the cells that the formula text refers to
	value value.Value
}

// Sheet is a spreadsheet. The zero value is not usable, use New.
type Sheet struct {
	cells      map[addr.Addr]*cell
	dependents map[addr.Addr][]addr.Addr // cell -> formulas that refer to it
	watchers   map[addr.Addr][]WatchFunc
	funcs      map[string]eval.Func
}

// New makes an empty sheet.
func New() *Sheet {
	return &Sheet{
		cells:      map[addr.Addr]*cell{},
		dependents: map[addr.Addr][]addr.Addr{},
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

// Set sets the input of one cell and updates the sheet.
func (s *Sheet) Set(name, input string) error {
	a, err := addr.Parse(name)
	if err != nil {
		return err
	}
	c, err := compile(input)
	if err != nil {
		return fmt.Errorf("%s: %w", name, err)
	}
	if c != nil && c.expr != nil && s.reaches(c.refs, a) {
		return fmt.Errorf("%s: %w", name, ErrCycle)
	}
	old := s.valueOf(a)
	s.define(a, c)
	s.update(a, old)
	return nil
}

// Apply sets the inputs of several cells and updates the sheet.
func (s *Sheet) Apply(edits []Edit) error {
	for i, e := range edits {
		if err := s.Set(e.Cell, e.Input); err != nil {
			return fmt.Errorf("edit %d: %w", i+1, err)
		}
	}
	return nil
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
	return &cell{input: input, expr: expr, refs: formula.Refs(expr)}, nil
}

// define replaces the input of the cell a and its references.
func (s *Sheet) define(a addr.Addr, c *cell) {
	if old, ok := s.cells[a]; ok {
		for _, r := range old.refs {
			s.dependents[r] = slices.DeleteFunc(s.dependents[r], func(d addr.Addr) bool { return d == a })
			if len(s.dependents[r]) == 0 {
				delete(s.dependents, r)
			}
		}
	}
	if c == nil {
		delete(s.cells, a)
		return
	}
	for _, r := range c.refs {
		s.dependents[r] = append(s.dependents[r], a)
	}
	s.cells[a] = c
}

// update brings the cell a up to date after a change, then each formula that
// refers to it. old is the value of a before the change.
func (s *Sheet) update(a addr.Addr, old value.Value) {
	if c, ok := s.cells[a]; ok && c.expr != nil {
		c.value = s.evaluate(c)
	}
	if v := s.valueOf(a); !v.Equal(old) {
		for _, fn := range s.watchers[a] {
			fn(a.String(), old, v)
		}
	}
	for _, d := range s.dependents[a] {
		s.update(d, s.valueOf(d))
	}
}

func (s *Sheet) evaluate(c *cell) value.Value {
	return eval.Eval(c.expr, &eval.Env{Read: s.valueOf, Funcs: s.funcs})
}

func (s *Sheet) valueOf(a addr.Addr) value.Value {
	if c, ok := s.cells[a]; ok {
		return c.value
	}
	return value.Empty
}

// reaches tells if target is in refs, or in the references of a formula in
// refs, at any depth.
func (s *Sheet) reaches(refs []addr.Addr, target addr.Addr) bool {
	seen := map[addr.Addr]bool{}
	stack := slices.Clone(refs)
	for len(stack) > 0 {
		a := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if a == target {
			return true
		}
		if seen[a] {
			continue
		}
		seen[a] = true
		if c, ok := s.cells[a]; ok {
			stack = append(stack, c.refs...)
		}
	}
	return false
}
