package db

import (
	"errors"
	"os"
	"strings"
	"testing"

	"example.com/minisql/table"
)

func open(t *testing.T) *DB {
	t.Helper()
	d, err := Open("../testdata")
	if err != nil {
		t.Fatal(err)
	}
	return d
}

func check(t *testing.T, d *DB, query, want string) {
	t.Helper()
	r, err := d.Query(query)
	if err != nil {
		t.Fatalf("%s: %v", query, err)
	}
	if got := Format(r); got != want {
		t.Errorf("%s:\ngot:\n%swant:\n%s", query, got, want)
	}
}

func checkError(t *testing.T, d *DB, query, code string) {
	t.Helper()
	_, err := d.Query(query)
	var e *Error
	if !errors.As(err, &e) || e.Code != code {
		t.Errorf("%s: error = %v; want code %s", query, err, code)
	}
}

func TestSelectWhereOrder(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT id, qty * price AS total FROM sales WHERE region = 'north' ORDER BY total DESC, id",
		"id | total\n6 | 99.99\n3 | 70.0\n1 | 25.0\n10 | 15.0\n")
	check(t, d, "select UPPER(Region) r, id from SALES where id < 3", "r | id\nNORTH | 1\nSOUTH | 2\n")
}

func TestNulls(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT id, region, qty FROM sales WHERE qty IS NULL OR region IS NULL ORDER BY 1",
		"id | region | qty\n4 | east | NULL\n7 | NULL | 4\n")
	check(t, d, "SELECT id FROM sales WHERE price > 50 AND rep IS NULL", "id\n6\n")
	check(t, d, "SELECT COALESCE(rep, '-') AS rep, id FROM sales ORDER BY rep, id LIMIT 3",
		"rep | id\n- | 6\nann | 1\nann | 3\n")
}

func TestExpressions(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT 7 / 2, -7 / 2, 7 % 3, 7.0 / 2, 'a' || 'b', LENGTH('héllo'), ROUND(2.345, 2) FROM sales LIMIT 1",
		"7 / 2 | -7 / 2 | 7 % 3 | 7.0 / 2 | 'a' || 'b' | LENGTH('héllo') | ROUND(2.345, 2)\n3 | -3 | 1 | 3.5 | ab | 5 | 2.35\n")
	check(t, d, "SELECT id FROM sales ORDER BY price DESC, id LIMIT 2 OFFSET 1", "id\n8\n2\n")
	check(t, d, "SELECT -9223372036854775808 AS m FROM sales LIMIT 1", "m\n-9223372036854775808\n")
}

func TestErrors(t *testing.T) {
	d := open(t)
	checkError(t, d, "SELECT FROM sales", "syntax")
	checkError(t, d, "SELECT id FROM nope", "unknown_table")
	checkError(t, d, "SELECT nope FROM sales", "unknown_column")
	checkError(t, d, "SELECT FOO(id) FROM sales", "unknown_function")
	checkError(t, d, "SELECT id + region FROM sales", "type")
	checkError(t, d, "SELECT id FROM sales ORDER BY 2", "ordinal")
	checkError(t, d, "SELECT id / 0 FROM sales", "division_by_zero")
	checkError(t, d, "SELECT 9223372036854775807 + id FROM sales", "overflow")
}

func TestReadTable(t *testing.T) {
	tb, err := table.Read("t", strings.NewReader("a:INT,b:TEXT\n1,x\n,\n"))
	if err != nil {
		t.Fatal(err)
	}
	d := New(tb)
	check(t, d, "SELECT * FROM T", "a | b\n1 | x\nNULL | NULL\n")
	if _, err := os.Stat("../testdata/sales.csv"); err != nil {
		t.Fatal(err)
	}
}
