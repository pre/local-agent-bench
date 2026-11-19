// Package addr parses and formats cell addresses such as "B7" and ranges
// such as "A1:C3".
package addr

import (
	"errors"
	"fmt"
	"strings"
)

// The largest column (XFD) and row of a sheet.
const (
	MaxCol = 16384
	MaxRow = 1048576
)

// ErrAddress is the error for a text that is not a valid address or range.
var ErrAddress = errors.New("invalid address")

// Addr is the address of one cell. Col and Row start at 1.
type Addr struct {
	Col int
	Row int
}

// Parse reads an address such as "A1" or "xfd1048576". Letters are not case
// sensitive. Absolute markers ("$A$1") are not supported.
func Parse(s string) (Addr, error) {
	col, rest, ok := splitColumn(s)
	if !ok || rest == "" || rest[0] == '0' {
		return Addr{}, fmt.Errorf("%w: %q", ErrAddress, s)
	}
	row := 0
	for _, r := range rest {
		if r < '0' || r > '9' {
			return Addr{}, fmt.Errorf("%w: %q", ErrAddress, s)
		}
		row = row*10 + int(r-'0')
		if row > MaxRow {
			return Addr{}, fmt.Errorf("%w: %q: row is too large", ErrAddress, s)
		}
	}
	if col > MaxCol {
		return Addr{}, fmt.Errorf("%w: %q: column is too large", ErrAddress, s)
	}
	return Addr{Col: col, Row: row}, nil
}

// MustParse is Parse for addresses that are known to be valid.
func MustParse(s string) Addr {
	a, err := Parse(s)
	if err != nil {
		panic(err)
	}
	return a
}

func splitColumn(s string) (int, string, bool) {
	col, i := 0, 0
	for i < len(s) {
		c := s[i]
		switch {
		case c >= 'A' && c <= 'Z':
			col = col*26 + int(c-'A'+1)
		case c >= 'a' && c <= 'z':
			col = col*26 + int(c-'a'+1)
		default:
			return col, s[i:], i > 0
		}
		if col > MaxCol {
			return col, "", false
		}
		i++
	}
	return col, "", false
}

// ColName gives the letters of a column: 1 is "A", 27 is "AA".
func ColName(col int) string {
	var b []byte
	for col > 0 {
		col--
		b = append(b, byte('A'+col%26))
		col /= 26
	}
	for i, j := 0, len(b)-1; i < j; i, j = i+1, j-1 {
		b[i], b[j] = b[j], b[i]
	}
	return string(b)
}

func (a Addr) String() string {
	return fmt.Sprintf("%s%d", ColName(a.Col), a.Row)
}

// Less orders addresses by row, then by column.
func Less(a, b Addr) bool {
	if a.Row != b.Row {
		return a.Row < b.Row
	}
	return a.Col < b.Col
}

// Compare is Less as a three-way comparison, for slices.SortFunc.
func Compare(a, b Addr) int {
	switch {
	case Less(a, b):
		return -1
	case Less(b, a):
		return 1
	}
	return 0
}

// Range is a rectangle of cells. From is the top left cell and To is the
// bottom right cell.
type Range struct {
	From Addr
	To   Addr
}

// ParseRange reads a range such as "A1:C3". The corners can be in any order.
func ParseRange(s string) (Range, error) {
	left, right, ok := strings.Cut(s, ":")
	if !ok {
		return Range{}, fmt.Errorf("%w: %q is not a range", ErrAddress, s)
	}
	a, err := Parse(left)
	if err != nil {
		return Range{}, err
	}
	b, err := Parse(right)
	if err != nil {
		return Range{}, err
	}
	return NewRange(a, b), nil
}

// NewRange makes the range with the corners a and b.
func NewRange(a, b Addr) Range {
	return Range{
		From: Addr{Col: min(a.Col, b.Col), Row: min(a.Row, b.Row)},
		To:   Addr{Col: max(a.Col, b.Col), Row: max(a.Row, b.Row)},
	}
}

// Size is the number of cells in the range.
func (r Range) Size() int {
	return (r.To.Col - r.From.Col + 1) * (r.To.Row - r.From.Row + 1)
}

// Cells gives the cells of the range by row, then by column.
func (r Range) Cells() []Addr {
	cells := make([]Addr, 0, r.Size())
	for row := r.From.Row; row <= r.To.Row; row++ {
		for col := r.From.Col; col <= r.To.Col; col++ {
			cells = append(cells, Addr{Col: col, Row: row})
		}
	}
	return cells
}

// Contains tells if the cell a is in the range.
func (r Range) Contains(a Addr) bool {
	return a.Col >= r.From.Col && a.Col <= r.To.Col && a.Row >= r.From.Row && a.Row <= r.To.Row
}

func (r Range) String() string {
	return r.From.String() + ":" + r.To.String()
}
