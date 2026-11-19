package db_test

import (
	"errors"
	"strings"
	"testing"

	"example.com/minisql/db"
	"example.com/minisql/table"
)

const ordersCSV = `id:INT,region:TEXT,product:TEXT,qty:INT,price:FLOAT,disc:FLOAT,big:INT,flag:BOOL
1,north,widget,10,2.5,0.0,9000000000000000000,true
2,south,gadget,3,10.0,-0.0,9000000000000000000,false
3,north,gadget,7,10.0,0.5,-9000000000000000000,true
4,east,widget,,2.5,,1,
5,south,widget,12,2.25,0.0,5,false
6,North,gizmo,1,99.99,,,true
7,,widget,4,2.5,0.5,,false
8,east,gizmo,2,95.0,0.25,7,true
9,south,gadget,5,,0.0,,false
10,north,widget,6,2.5,-0.0,3,true
`

func open(t *testing.T) *db.DB {
	t.Helper()
	tb, err := table.Read("orders", strings.NewReader(ordersCSV))
	if err != nil {
		t.Fatal(err)
	}
	return db.New(tb)
}

func check(t *testing.T, d *db.DB, query string, want ...string) {
	t.Helper()
	r, err := d.Query(query)
	if err != nil {
		t.Errorf("%s: %v", query, err)
		return
	}
	w := strings.Join(want, "\n") + "\n"
	if got := db.Format(r); got != w {
		t.Errorf("%s:\ngot:\n%swant:\n%s", query, got, w)
	}
}

func checkError(t *testing.T, d *db.DB, query, code string) {
	t.Helper()
	_, err := d.Query(query)
	var e *db.Error
	if !errors.As(err, &e) || e.Code != code {
		t.Errorf("%s: error = %v; want code %s", query, err, code)
	}
}

func TestCountForms(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT region, COUNT(*), COUNT(qty), COUNT(DISTINCT product) FROM orders GROUP BY region",
		"region | COUNT(*) | COUNT(qty) | COUNT(DISTINCT product)",
		"north | 3 | 3 | 2",
		"south | 3 | 3 | 2",
		"east | 2 | 1 | 2",
		"North | 1 | 1 | 1",
		"NULL | 1 | 1 | 1")
}

func TestGroupOrderAfterWhere(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT product, COUNT(*) AS n FROM orders WHERE id > 2 GROUP BY product",
		"product | n", "gadget | 2", "widget | 4", "gizmo | 2")
}

func TestSumAvgTypes(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT product, SUM(qty), SUM(price), AVG(qty), AVG(price) FROM orders GROUP BY product ORDER BY product",
		"product | SUM(qty) | SUM(price) | AVG(qty) | AVG(price)",
		"gadget | 15 | 20.0 | 5.0 | 10.0",
		"gizmo | 3 | 194.99 | 1.5 | 97.495",
		"widget | 32 | 12.25 | 8.0 | 2.45")
}

func TestEmptyInput(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT COUNT(*), COUNT(qty), SUM(qty), AVG(price), MIN(region), MAX(qty) FROM orders WHERE id > 100",
		"COUNT(*) | COUNT(qty) | SUM(qty) | AVG(price) | MIN(region) | MAX(qty)",
		"0 | 0 | NULL | NULL | NULL | NULL")
	check(t, d, "SELECT region, COUNT(*) FROM orders WHERE id > 100 GROUP BY region", "region | COUNT(*)")
	check(t, d, "SELECT COUNT(*) FROM orders WHERE id > 100 HAVING COUNT(*) > 0", "COUNT(*)")
	check(t, d, "SELECT SUM(qty) AS s FROM orders WHERE qty IS NULL", "s", "NULL")
}

func TestIdenticalValuesGroup(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT disc, COUNT(*) FROM orders GROUP BY disc",
		"disc | COUNT(*)", "0.0 | 5", "0.5 | 2", "NULL | 2", "0.25 | 1")
	check(t, d, "SELECT COUNT(DISTINCT disc), SUM(DISTINCT disc) FROM orders",
		"COUNT(DISTINCT disc) | SUM(DISTINCT disc)", "3 | 0.75")
}

func TestExactIntegerSum(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT SUM(big) FROM orders", "SUM(big)", "9000000000000000016")
	checkError(t, d, "SELECT SUM(big) FROM orders WHERE id <> 3", "overflow")
	check(t, d, "SELECT AVG(big) FROM orders WHERE id <> 3", "AVG(big)", "3000000000000000000.0")
	check(t, d, "SELECT region, SUM(big) FROM orders WHERE big > 0 AND region = 'east' GROUP BY region",
		"region | SUM(big)", "east | 8")
}

func TestGroupByItems(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT LOWER(region) AS r, COUNT(*) FROM orders GROUP BY 1 ORDER BY 1",
		"r | COUNT(*)", "NULL | 1", "east | 2", "north | 4", "south | 3")
	check(t, d, "SELECT LOWER(region) AS r, COUNT(*) AS n FROM orders GROUP BY r ORDER BY n DESC, r",
		"r | n", "north | 4", "south | 3", "east | 2", "NULL | 1")
	check(t, d, "SELECT qty % 2 AS parity, COUNT(*) FROM orders GROUP BY qty % 2",
		"parity | COUNT(*)", "0 | 5", "1 | 4", "NULL | 1")
	check(t, d, "SELECT (qty % 2) * 10 + 1 AS x, COUNT(*) FROM orders GROUP BY QTY % 2",
		"x | COUNT(*)", "1 | 5", "11 | 4", "NULL | 1")
	check(t, d, "SELECT Region, COUNT(*) FROM orders GROUP BY REGION",
		"region | COUNT(*)", "north | 3", "south | 3", "east | 2", "North | 1", "NULL | 1")
}

func TestGroupByErrors(t *testing.T) {
	d := open(t)
	checkError(t, d, "SELECT LOWER(product) AS region, COUNT(*) FROM orders GROUP BY region", "grouping")
	checkError(t, d, "SELECT region, COUNT(*) FROM orders GROUP BY 3", "ordinal")
	checkError(t, d, "SELECT region, COUNT(*) FROM orders GROUP BY 2", "aggregate")
	checkError(t, d, "SELECT region FROM orders GROUP BY nope", "unknown_column")
}

func TestGroupingErrors(t *testing.T) {
	d := open(t)
	checkError(t, d, "SELECT region, qty FROM orders GROUP BY region", "grouping")
	checkError(t, d, "SELECT * FROM orders GROUP BY region", "grouping")
	checkError(t, d, "SELECT region FROM orders GROUP BY LOWER(region)", "grouping")
	checkError(t, d, "SELECT COUNT(*) FROM orders ORDER BY qty", "grouping")
	checkError(t, d, "SELECT region, COUNT(*) FROM orders GROUP BY region HAVING qty > 1", "grouping")
	checkError(t, d, "SELECT qty + COUNT(*) FROM orders", "grouping")
	checkError(t, d, "SELECT nope, COUNT(*) FROM orders", "unknown_column")
	check(t, d, "SELECT * FROM orders WHERE id < 3 GROUP BY id, region, product, qty, price, disc, big, flag",
		"id | region | product | qty | price | disc | big | flag",
		"1 | north | widget | 10 | 2.5 | 0.0 | 9000000000000000000 | TRUE",
		"2 | south | gadget | 3 | 10.0 | 0.0 | 9000000000000000000 | FALSE")
}

func TestAggregateMisuse(t *testing.T) {
	d := open(t)
	checkError(t, d, "SELECT id FROM orders WHERE COUNT(*) > 1", "aggregate")
	checkError(t, d, "SELECT COUNT(*) FROM orders GROUP BY COUNT(*)", "aggregate")
	checkError(t, d, "SELECT SUM(COUNT(*)) FROM orders", "aggregate")
	checkError(t, d, "SELECT MAX(AVG(qty)) FROM orders GROUP BY region", "aggregate")
	checkError(t, d, "SELECT SUM(region) FROM orders", "type")
	checkError(t, d, "SELECT AVG(flag) FROM orders", "type")
	checkError(t, d, "SELECT SUM(10 / (qty - 3)) FROM orders", "division_by_zero")
}

func TestHaving(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT region, SUM(qty) AS s FROM orders GROUP BY region HAVING COUNT(*) >= 2 AND MAX(price) > 5 ORDER BY s",
		"region | s", "east | 2", "south | 20", "north | 23")
	check(t, d, "SELECT COUNT(*) FROM orders HAVING SUM(qty) > 40", "COUNT(*)", "10")
	check(t, d, "SELECT COUNT(*) FROM orders HAVING SUM(qty) > 60", "COUNT(*)")
	check(t, d, "SELECT region FROM orders GROUP BY region HAVING MAX(qty) > 5", "region", "north", "south")
	checkError(t, d, "SELECT region, COUNT(*) AS n FROM orders GROUP BY region HAVING n > 1", "unknown_column")
}

func TestOrderByInAggregateQuery(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT product FROM orders GROUP BY product ORDER BY COUNT(*) DESC, product",
		"product", "widget", "gadget", "gizmo")
	check(t, d, "SELECT region, MIN(qty), MAX(product) FROM orders GROUP BY region ORDER BY 2 DESC LIMIT 2 OFFSET 1",
		"region | MIN(qty) | MAX(product)", "NULL | 4 | widget", "south | 3 | widget")
	check(t, d, "SELECT COUNT(*) AS n, region FROM orders GROUP BY region ORDER BY n, region DESC",
		"n | region", "1 | North", "1 | NULL", "2 | east", "3 | south", "3 | north")
}

func TestDistinct(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT DISTINCT product FROM orders", "product", "widget", "gadget", "gizmo")
	check(t, d, "SELECT DISTINCT disc FROM orders ORDER BY disc DESC", "disc", "0.5", "0.25", "0.0", "NULL")
	checkError(t, d, "SELECT DISTINCT region FROM orders ORDER BY qty", "distinct")
	check(t, d, "SELECT DISTINCT LOWER(region) AS r FROM orders ORDER BY lower(Region)", "r", "NULL", "east", "north", "south")
	check(t, d, "SELECT DISTINCT COUNT(*) AS n FROM orders GROUP BY region ORDER BY n", "n", "1", "2", "3")
	check(t, d, "SELECT DISTINCT product, qty > 4 AS many FROM orders WHERE qty IS NOT NULL LIMIT 4 OFFSET 1",
		"product | many", "gadget | FALSE", "gadget | TRUE", "gizmo | FALSE", "widget | FALSE")
}

func TestDistinctAggregates(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT SUM(DISTINCT price), AVG(DISTINCT price), MIN(DISTINCT region), COUNT(DISTINCT region) FROM orders",
		"SUM(DISTINCT price) | AVG(DISTINCT price) | MIN(DISTINCT region) | COUNT(DISTINCT region)",
		"209.74 | 41.948 | North | 4")
	check(t, d, "SELECT region, COUNT(DISTINCT qty % 3) AS k FROM orders GROUP BY region ORDER BY region",
		"region | k", "NULL | 1", "North | 1", "east | 1", "north | 2", "south | 2")
}

func TestMinMaxAndNames(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT MIN(flag), MAX(flag), MIN(price), MAX(region), MIN(-qty) FROM orders",
		"MIN(flag) | MAX(flag) | MIN(price) | MAX(region) | MIN(-qty)",
		"FALSE | TRUE | 2.25 | south | -12")
	check(t, d, "SELECT COUNT(*), count(distinct Qty), sum(qty*price), AVG(price) + 1 FROM orders WHERE id = 1",
		"COUNT(*) | COUNT(DISTINCT Qty) | SUM(qty * price) | AVG(price) + 1",
		"1 | 1 | 25.0 | 3.5")
}

func TestVersionOneQueries(t *testing.T) {
	d := open(t)
	check(t, d, "SELECT id, qty * price AS total FROM orders WHERE region = 'north' ORDER BY total DESC, id",
		"id | total", "3 | 70.0", "1 | 25.0", "10 | 15.0")
	check(t, d, "SELECT id FROM orders WHERE disc = 0 ORDER BY big, id DESC LIMIT 3", "id", "9", "10", "5")
	checkError(t, d, "SELECT id FROM orders ORDER BY 2", "ordinal")
	checkError(t, d, "SELECT id FROM orders WHERE region", "type")
}
