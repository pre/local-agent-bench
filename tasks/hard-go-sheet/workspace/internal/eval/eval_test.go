package eval

import (
	"testing"

	"example.com/sheet/internal/addr"
	"example.com/sheet/internal/formula"
	"example.com/sheet/value"
)

func run(t *testing.T, src string, cells map[string]value.Value) (value.Value, []string) {
	t.Helper()
	e, err := formula.Parse(src)
	if err != nil {
		t.Fatalf("Parse(%q): %v", src, err)
	}
	var reads []string
	env := &Env{
		Read: func(a addr.Addr) value.Value {
			reads = append(reads, a.String())
			return cells[a.String()]
		},
		Funcs: map[string]Func{
			"TWICE": func(args []value.Value) value.Value { return value.Number(2 * args[0].Num()) },
		},
	}
	return Eval(e, env), reads
}

func TestArithmetic(t *testing.T) {
	cells := map[string]value.Value{"A1": value.Number(3), "A2": value.Text("x")}
	cases := map[string]string{
		"1+2*3":        "7",
		"-2^2":         "4",
		"2^3^2":        "512",
		"A1/0":         value.ErrDivZero,
		"A1+A2":        value.ErrValue,
		"A1&A2":        "3x",
		"B1+1":         "1",
		"A1>2":         "TRUE",
		`"a"<"b"`:      "TRUE",
		"1<\"a\"":      "TRUE",
		"ROUND(2.5,0)": "3",
		"ABS(-4)":      "4",
		"NOPE(1)":      value.ErrName,
		"TWICE(A1)":    "6",
		"10^400":       value.ErrNum,
	}
	for src, want := range cases {
		got, _ := run(t, src, cells)
		if got.String() != want {
			t.Errorf("%s = %v; want %s", src, got, want)
		}
	}
}

func TestIfReadsOneBranch(t *testing.T) {
	cells := map[string]value.Value{"A1": value.Number(1), "B1": value.Number(10), "C1": value.Number(20)}
	got, reads := run(t, "IF(A1>0, B1, C1)", cells)
	if got.String() != "10" {
		t.Fatalf("value = %v", got)
	}
	if len(reads) != 2 || reads[0] != "A1" || reads[1] != "B1" {
		t.Fatalf("reads = %v; want [A1 B1]", reads)
	}
}

func TestAggregates(t *testing.T) {
	cells := map[string]value.Value{
		"A1": value.Number(1), "A2": value.Number(5), "A3": value.Text("t"), "A4": value.Boolean(true),
	}
	cases := map[string]string{
		"SUM(A1:A5)":     "6",
		"COUNT(A1:A5)":   "2",
		"AVERAGE(A1:A2)": "3",
		"MAX(A1:A5, 9)":  "9",
		"MIN(B1:B3)":     "0",
		"AVERAGE(B1:B3)": value.ErrDivZero,
	}
	for src, want := range cases {
		got, _ := run(t, src, cells)
		if got.String() != want {
			t.Errorf("%s = %v; want %s", src, got, want)
		}
	}
}
