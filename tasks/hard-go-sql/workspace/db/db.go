// Package db is the entry point of minisql: a set of tables and queries on
// them.
package db

import (
	"fmt"
	"strings"

	"example.com/minisql/exec"
	"example.com/minisql/plan"
	"example.com/minisql/sql"
	"example.com/minisql/table"
)

// Error is the error type of all failed queries. See docs/SQL.md, "Errors".
type Error = sql.Error

// Result is the result of a query.
type Result = exec.Result

// DB is a set of tables, by lower case name.
type DB struct {
	tables map[string]*table.Table
}

// New makes a database with the tables.
func New(tables ...*table.Table) *DB {
	d := &DB{tables: map[string]*table.Table{}}
	for _, t := range tables {
		d.tables[strings.ToLower(t.Name)] = t
	}
	return d
}

// Open reads each *.csv file of a directory as a table.
func Open(dir string) (*DB, error) {
	ts, err := table.LoadDir(dir)
	if err != nil {
		return nil, err
	}
	return New(ts...), nil
}

// Query parses, checks and runs one SELECT statement. All errors are *Error.
func (d *DB) Query(src string) (*Result, error) {
	s, err := sql.Parse(src)
	if err != nil {
		return nil, err
	}
	q, err := plan.Build(s, d.tables)
	if err != nil {
		return nil, err
	}
	return exec.Run(q)
}

// Format writes a result as text: a header line with the column names, then
// one line for each row. Fields are separated by " | ".
func Format(r *Result) string {
	var b strings.Builder
	b.WriteString(strings.Join(r.Columns, " | "))
	b.WriteByte('\n')
	for _, row := range r.Rows {
		for i, v := range row {
			if i > 0 {
				b.WriteString(" | ")
			}
			b.WriteString(v.String())
		}
		b.WriteByte('\n')
	}
	return b.String()
}

// MustQuery is Query for tests and examples. It panics on an error.
func (d *DB) MustQuery(src string) string {
	r, err := d.Query(src)
	if err != nil {
		panic(fmt.Sprintf("%s: %v", src, err))
	}
	return Format(r)
}
