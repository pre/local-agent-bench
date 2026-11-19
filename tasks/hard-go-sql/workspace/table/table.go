// Package table loads tables from CSV files.
//
// The first line of a file is the header: "name:TYPE" for each column, for
// example "id:INT,name:TEXT,price:FLOAT,active:BOOL". An empty field is NULL.
// The name of the table is the file name without ".csv".
package table

import (
	"encoding/csv"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"example.com/minisql/value"
)

// Column is the name and the type of a column.
type Column struct {
	Name string
	Type value.Type
}

// Table is a table in memory.
type Table struct {
	Name    string
	Columns []Column
	Rows    [][]value.Value
}

// Index gives the position of a column, not case sensitive, or -1.
func (t *Table) Index(name string) int {
	for i, c := range t.Columns {
		if strings.EqualFold(c.Name, name) {
			return i
		}
	}
	return -1
}

// Read reads a table in CSV form.
func Read(name string, r io.Reader) (*Table, error) {
	cr := csv.NewReader(r)
	cr.FieldsPerRecord = -1
	header, err := cr.Read()
	if err != nil {
		return nil, fmt.Errorf("table %s: header: %w", name, err)
	}
	t := &Table{Name: name}
	for _, h := range header {
		n, ty, ok := strings.Cut(strings.TrimSpace(h), ":")
		typ, okType := value.ParseType(ty)
		if !ok || !okType || n == "" {
			return nil, fmt.Errorf("table %s: bad column %q, expected name:TYPE", name, h)
		}
		if t.Index(n) >= 0 {
			return nil, fmt.Errorf("table %s: two columns have the name %q", name, n)
		}
		t.Columns = append(t.Columns, Column{Name: n, Type: typ})
	}
	line := 1
	for {
		rec, err := cr.Read()
		if err == io.EOF {
			break
		}
		line++
		if err != nil {
			return nil, fmt.Errorf("table %s: line %d: %w", name, line, err)
		}
		if len(rec) != len(t.Columns) {
			return nil, fmt.Errorf("table %s: line %d: %d fields, expected %d", name, line, len(rec), len(t.Columns))
		}
		row := make([]value.Value, len(rec))
		for i, field := range rec {
			v, err := parseField(field, t.Columns[i].Type)
			if err != nil {
				return nil, fmt.Errorf("table %s: line %d: column %s: %w", name, line, t.Columns[i].Name, err)
			}
			row[i] = v
		}
		t.Rows = append(t.Rows, row)
	}
	return t, nil
}

func parseField(s string, typ value.Type) (value.Value, error) {
	if s == "" {
		return value.NullValue, nil
	}
	switch typ {
	case value.Int:
		i, err := strconv.ParseInt(strings.TrimSpace(s), 10, 64)
		if err != nil {
			return value.NullValue, fmt.Errorf("bad INT %q", s)
		}
		return value.NewInt(i), nil
	case value.Float:
		f, err := strconv.ParseFloat(strings.TrimSpace(s), 64)
		if err != nil || math.IsInf(f, 0) || math.IsNaN(f) {
			return value.NullValue, fmt.Errorf("bad FLOAT %q", s)
		}
		return value.NewFloat(f), nil
	case value.Bool:
		switch strings.ToLower(strings.TrimSpace(s)) {
		case "true":
			return value.NewBool(true), nil
		case "false":
			return value.NewBool(false), nil
		}
		return value.NullValue, fmt.Errorf("bad BOOL %q", s)
	}
	return value.NewText(s), nil
}

// LoadDir reads each *.csv file of a directory.
func LoadDir(dir string) ([]*Table, error) {
	paths, err := filepath.Glob(filepath.Join(dir, "*.csv"))
	if err != nil {
		return nil, err
	}
	var out []*Table
	for _, p := range paths {
		f, err := os.Open(p)
		if err != nil {
			return nil, err
		}
		t, err := Read(strings.TrimSuffix(filepath.Base(p), ".csv"), f)
		f.Close()
		if err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, nil
}
