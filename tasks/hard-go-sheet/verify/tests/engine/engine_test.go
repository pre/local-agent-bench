package engine_test

import (
	"errors"
	"fmt"
	"maps"
	"slices"
	"strings"
	"testing"
	"time"

	"example.com/sheet/engine"
	"example.com/sheet/value"
)

// counter counts the calls of the custom function T(name, x), which gives x.
type counter map[string]int

type fixture struct {
	t     *testing.T
	s     *engine.Sheet
	count counter
	seen  [][]value.Value // arguments of SEEN(...)
}

func newFixture(t *testing.T) *fixture {
	t.Helper()
	f := &fixture{t: t, s: engine.New(), count: counter{}}
	err := f.s.RegisterFunc("T", func(args []value.Value) value.Value {
		if len(args) != 2 {
			return value.Error(value.ErrValue)
		}
		f.count[args[0].Str()]++
		return args[1]
	})
	if err != nil {
		t.Fatal(err)
	}
	err = f.s.RegisterFunc("SEEN", func(args []value.Value) value.Value {
		f.seen = append(f.seen, slices.Clone(args))
		s := 0.0
		for _, a := range args {
			s += a.Num()
		}
		return value.Number(s)
	})
	if err != nil {
		t.Fatal(err)
	}
	return f
}

func (f *fixture) set(cell, input string) {
	f.t.Helper()
	if err := f.s.Set(cell, input); err != nil {
		f.t.Fatalf("Set(%s, %q): %v", cell, input, err)
	}
}

func (f *fixture) apply(edits ...string) {
	f.t.Helper()
	if err := f.s.Apply(edits2(edits)); err != nil {
		f.t.Fatalf("Apply(%q): %v", edits, err)
	}
}

func edits2(pairs []string) []engine.Edit {
	var out []engine.Edit
	for i := 0; i+1 < len(pairs); i += 2 {
		out = append(out, engine.Edit{Cell: pairs[i], Input: pairs[i+1]})
	}
	return out
}

func (f *fixture) expect(cell, want string) {
	f.t.Helper()
	if got := f.s.Value(cell).String(); got != want {
		f.t.Errorf("%s = %q; want %q", cell, got, want)
	}
}

// evals runs fn and gives the counts of T calls during fn.
func (f *fixture) evals(fn func()) counter {
	f.t.Helper()
	before := maps.Clone(f.count)
	fn()
	diff := counter{}
	for k, v := range f.count {
		if d := v - before[k]; d != 0 {
			diff[k] = d
		}
	}
	return diff
}

func (f *fixture) expectEvals(what string, got counter, want counter) {
	f.t.Helper()
	if !maps.Equal(got, want) {
		f.t.Errorf("%s: evaluations = %v; want %v", what, got, want)
	}
}

type call struct{ cell, old, new string }

func (c call) String() string { return fmt.Sprintf("%s:%s->%s", c.cell, c.old, c.new) }

func watchAll(t *testing.T, s *engine.Sheet, calls *[]call, cells ...string) {
	t.Helper()
	for _, c := range cells {
		if err := s.Watch(c, func(cell string, old, new value.Value) {
			*calls = append(*calls, call{cell, old.String(), new.String()})
		}); err != nil {
			t.Fatal(err)
		}
	}
}

func TestBasics(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "2", "A2", "=A1*3", "A3", "=SUM(A1:A2)", "A4", `=IF(A3>5, "hi", "lo")`, "A5", "=A1/0", "A6", "=A5+1")
	f.expect("A2", "6")
	f.expect("A3", "8")
	f.expect("A4", "hi")
	f.expect("A6", value.ErrDivZero)
	f.set("A1", "1")
	f.expect("A3", "4")
	f.expect("A4", "lo")
	f.set("A2", "")
	f.expect("A3", "1")
	if f.s.Input("A2") != "" || slices.Contains(f.s.Cells(), "A2") {
		t.Error("A2 must be empty")
	}
	if got := f.s.Cells(); !slices.Equal(got, []string{"A1", "A3", "A4", "A5", "A6"}) {
		t.Errorf("Cells = %v", got)
	}
	if err := f.s.Set("A7", "=(1"); !errors.Is(err, engine.ErrSyntax) {
		t.Errorf("syntax error = %v", err)
	}
	if err := f.s.Set("7A", "1"); !errors.Is(err, engine.ErrAddress) {
		t.Errorf("address error = %v", err)
	}
}

func TestDiamondOnce(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "1",
		"B1", `=T("B1", A1+1)`,
		"C1", `=T("C1", A1*2)`,
		"D1", `=T("D1", B1+C1)`,
		"E1", `=T("E1", D1+B1)`)
	f.expect("E1", "6")
	got := f.evals(func() { f.set("A1", "5") })
	f.expectEvals("Set(A1, 5)", got, counter{"B1": 1, "C1": 1, "D1": 1, "E1": 1})
	f.expect("D1", "16")
	f.expect("E1", "22")
}

func TestLadderCounts(t *testing.T) {
	f := newFixture(t)
	const depth = 20
	var edits []string
	edits = append(edits, "A1", "1")
	prev := "A1"
	for i := 1; i <= depth; i++ {
		b, c, d := fmt.Sprintf("B%d", i), fmt.Sprintf("C%d", i), fmt.Sprintf("D%d", i)
		edits = append(edits,
			b, fmt.Sprintf(`=T("%s", %s+1)`, b, prev),
			c, fmt.Sprintf(`=T("%s", %s-1)`, c, prev),
			d, fmt.Sprintf(`=T("%s", (%s+%s)/2+1)`, d, b, c))
		prev = d
	}
	f.apply(edits...)
	f.expect(prev, fmt.Sprint(1+depth))
	for round := 2; round <= 4; round++ {
		got := f.evals(func() { f.set("A1", fmt.Sprint(round)) })
		total := 0
		for name, n := range got {
			total += n
			if n != 1 {
				t.Errorf("round %d: %s evaluated %d times; want 1", round, name, n)
			}
		}
		if total != 3*depth {
			t.Errorf("round %d: %d evaluations; want %d", round, total, 3*depth)
		}
		f.expect(prev, fmt.Sprint(round+depth))
	}
}

func TestConsistentReads(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "1",
		"B1", "=A1+1",
		"C1", "=B1*2",
		"D1", "=SEEN(A1, B1, C1)",
		"E1", "=SEEN(C1, D1)")
	for _, v := range []string{"2", "7", "-3", "10"} {
		f.seen = nil
		f.set("A1", v)
		if len(f.seen) != 2 {
			t.Errorf("Set(A1, %s): SEEN called %d times; want 2", v, len(f.seen))
		}
		for _, args := range f.seen {
			if len(args) == 3 {
				a, b, c := args[0].Num(), args[1].Num(), args[2].Num()
				if b != a+1 || c != 2*b {
					t.Errorf("Set(A1, %s): D1 read A1=%v B1=%v C1=%v, which is not a state of the sheet", v, a, b, c)
				}
			} else if len(args) == 2 {
				a := f.s.Value("A1").Num()
				c, d := args[0].Num(), args[1].Num()
				if c != 2*(a+1) || d != a+(a+1)+c {
					t.Errorf("Set(A1, %s): E1 read C1=%v D1=%v before their final values", v, c, d)
				}
			}
		}
	}
}

func TestCutoff(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "3",
		"B1", `=T("B1", A1*0)`,
		"C1", `=T("C1", B1+1)`,
		"D1", `=T("D1", C1*2)`,
		"B2", `=T("B2", ROUND(A1/10, 0))`,
		"C2", `=T("C2", B2+100)`)
	got := f.evals(func() { f.set("A1", "4") })
	f.expectEvals("Set(A1, 4)", got, counter{"B1": 1, "B2": 1})
	got = f.evals(func() { f.set("A1", "7") })
	f.expectEvals("Set(A1, 7)", got, counter{"B1": 1, "B2": 1, "C2": 1})
	f.expect("C2", "101")
	f.expect("D1", "2")
}

func TestSameValueNoEvaluation(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "1", "A2", "x", "A3", "TRUE",
		"B1", `=T("B1", A1)`, "B2", `=T("B2", A2)`, "B3", `=T("B3", A3)`)
	var calls []call
	watchAll(t, f.s, &calls, "A1", "B1")
	got := f.evals(func() {
		f.set("A1", "1.0")
		f.set("A2", "x")
		f.set("A3", "true")
		f.apply("A1", "1", "A2", "x")
	})
	f.expectEvals("inputs with the same values", got, counter{})
	got = f.evals(func() { f.set("A1", "0") })
	f.expectEvals("Set(A1, 0)", got, counter{"B1": 1})
	got = f.evals(func() { f.set("A1", "-0") })
	f.expectEvals("Set(A1, -0)", got, counter{})
	if want := []call{{"A1", "1", "0"}, {"B1", "1", "0"}}; !slices.Equal(calls, want) {
		t.Errorf("watch calls = %v; want %v", calls, want)
	}
}

func TestDynamicReads(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "1", "B1", "10", "D1", "20",
		"C1", `=T("C1", IF(A1>0, B1, D1))`,
		"E1", `=T("E1", C1+1)`)
	f.expect("E1", "11")
	f.expectEvals("change of the unselected branch", f.evals(func() { f.set("D1", "21") }), counter{})
	f.expectEvals("change of the selected branch", f.evals(func() { f.set("B1", "11") }), counter{"C1": 1, "E1": 1})
	f.expectEvals("change of the condition", f.evals(func() { f.set("A1", "-1") }), counter{"C1": 1, "E1": 1})
	f.expect("E1", "22")
	f.expectEvals("change of the old branch", f.evals(func() { f.set("B1", "12") }), counter{})
	f.expectEvals("change of the new branch", f.evals(func() { f.set("D1", "30") }), counter{"C1": 1, "E1": 1})
	f.expectEvals("condition stays false", f.evals(func() { f.set("A1", "-5") }), counter{"C1": 1})
	f.expect("E1", "31")
}

func TestReadsOfEmptyCell(t *testing.T) {
	f := newFixture(t)
	f.set("B1", `=T("B1", A9+1)`)
	f.set("C1", `=T("C1", B1*2)`)
	f.expect("C1", "2")
	f.expectEvals("Set(A9, 5)", f.evals(func() { f.set("A9", "5") }), counter{"B1": 1, "C1": 1})
	f.expect("C1", "12")
	f.expectEvals("Set(A9, \"\")", f.evals(func() { f.set("A9", "") }), counter{"B1": 1, "C1": 1})
	f.expect("C1", "2")
	f.expectEvals("Set(A9, 0)", f.evals(func() { f.set("A9", "0") }), counter{"B1": 1})
	f.expectEvals("Set(A8, 1)", f.evals(func() { f.set("A8", "1") }), counter{})
}

func TestApplyOneUpdate(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "1", "A2", "2", "A3", "3",
		"B1", `=T("B1", A1+A2+A3)`,
		"C1", `=T("C1", B1*10)`)
	var calls []call
	watchAll(t, f.s, &calls, "A1", "B1", "C1")
	got := f.evals(func() { f.apply("A1", "10", "A2", "20", "A3", "30") })
	f.expectEvals("Apply of three cells", got, counter{"B1": 1, "C1": 1})
	if want := []call{{"A1", "1", "10"}, {"B1", "6", "60"}, {"C1", "60", "600"}}; !slices.Equal(calls, want) {
		t.Errorf("watch calls = %v; want %v", calls, want)
	}

	calls = nil
	got = f.evals(func() { f.apply("A2", "21", "A3", "29") })
	f.expectEvals("Apply with the same sum", got, counter{"B1": 1})
	f.expect("B1", "60")
	if len(calls) != 0 {
		t.Errorf("watch calls = %v; want none", calls)
	}

	calls = nil
	got = f.evals(func() { f.apply("A1", "99", "A1", "10") })
	f.expectEvals("Apply that sets A1 back to its value", got, counter{})
	if len(calls) != 0 {
		t.Errorf("watch calls = %v; want none", calls)
	}

	got = f.evals(func() { f.apply("B1", `=T("B1", A1)`, "A1", "600", "B1", `=T("B1", A1/10)`) })
	f.expectEvals("Apply that sets B1 twice", got, counter{"B1": 1})
	f.expect("B1", "60")
	if f.s.Input("B1") != `=T("B1", A1/10)` {
		t.Errorf("Input(B1) = %q; the last edit of a cell must apply", f.s.Input("B1"))
	}
}

func TestApplyAtomic(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "1", "B1", `=T("B1", A1*2)`, "C1", `=T("C1", B1+1)`)
	var calls []call
	watchAll(t, f.s, &calls, "A1", "B1", "C1", "D1")
	check := func(what string, err error, target error) {
		t.Helper()
		if !errors.Is(err, target) {
			t.Errorf("%s: error = %v; want %v", what, err, target)
		}
		if f.s.Input("A1") != "1" || f.s.Input("D1") != "" || f.s.Value("C1").String() != "3" {
			t.Errorf("%s: the sheet changed: A1=%q D1=%q C1=%v", what, f.s.Input("A1"), f.s.Input("D1"), f.s.Value("C1"))
		}
		if len(calls) != 0 {
			t.Errorf("%s: watch calls = %v; want none", what, calls)
		}
	}
	var err error
	got := f.evals(func() { err = f.s.Apply(edits2([]string{"A1", "5", "D1", "=A1+1", "E1", "=SUM(1,"})) })
	check("Apply with a syntax error", err, engine.ErrSyntax)
	f.expectEvals("Apply with a syntax error", got, counter{})
	got = f.evals(func() { err = f.s.Apply(edits2([]string{"A1", "5", "D1", "=A1+1", "E0", "1"})) })
	check("Apply with a bad address", err, engine.ErrAddress)
	f.expectEvals("Apply with a bad address", got, counter{})
	got = f.evals(func() { err = f.s.Apply(edits2([]string{"A1", "=C1", "D1", "7"})) })
	check("Apply with a cycle", err, engine.ErrCycle)
	f.expectEvals("Apply with a cycle", got, counter{})
	got = f.evals(func() { err = f.s.Set("B1", `=T("B1", C1)`) })
	check("Set with a cycle", err, engine.ErrCycle)
	f.expectEvals("Set with a cycle", got, counter{})
	if f.s.Input("B1") != `=T("B1", A1*2)` {
		t.Errorf("Input(B1) = %q after a rejected Set", f.s.Input("B1"))
	}
	f.expectEvals("Set(A1, 2) after the errors", f.evals(func() { f.set("A1", "2") }), counter{"B1": 1, "C1": 1})
}

func TestCycleCheckUsesNewInputs(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "=B1+1", "B1", "=C1")
	if err := f.s.Apply(edits2([]string{"C1", "=A1", "A1", "3"})); err != nil {
		t.Fatalf("Apply that removes the old reference before the new one: %v", err)
	}
	f.expect("C1", "3")
	f.expect("B1", "3")
	err := f.s.Apply(edits2([]string{"D1", "=E1", "E1", "=D1"}))
	if !errors.Is(err, engine.ErrCycle) {
		t.Errorf("Apply(D1=E1, E1=D1) = %v; want ErrCycle", err)
	}
	err = f.s.Set("F1", `=IF(TRUE, 1, F2)`)
	if err != nil {
		t.Fatal(err)
	}
	if err := f.s.Set("F2", "=F1"); !errors.Is(err, engine.ErrCycle) {
		t.Errorf("a cycle through the unselected branch of IF: error = %v; want ErrCycle", err)
	}
	if err := f.s.Set("G5", "=SUM(G1:G9)"); !errors.Is(err, engine.ErrCycle) {
		t.Errorf("a range that contains the cell: error = %v; want ErrCycle", err)
	}
}

func TestWatchOrder(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "1", "C1", "=A1+1", "B2", "=A1*2", "A3", "=A1-1", "AA1", "=A1")
	var calls []string
	add := func(cell, tag string) {
		if err := f.s.Watch(cell, func(c string, old, new value.Value) {
			calls = append(calls, fmt.Sprintf("%s%s:%v->%v", tag, c, old, new))
		}); err != nil {
			t.Fatal(err)
		}
	}
	add("a3", "")
	add("B2", "x")
	add("aa1", "")
	add("C1", "")
	add("B2", "y")
	add("A1", "")
	f.set("A1", "5")
	want := []string{"A1:1->5", "C1:2->6", "AA1:1->5", "xB2:2->10", "yB2:2->10", "A3:0->4"}
	if !slices.Equal(calls, want) {
		t.Errorf("watch calls =\n %v\nwant\n %v", calls, want)
	}
}

func TestWatchFinalValuesOnly(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "2", "B1", "=A1*10", "C1", "=0-A1*10", "D1", "=B1+C1+A1", "E1", "=IF(D1>2, B1, C1)")
	var calls []call
	watchAll(t, f.s, &calls, "D1", "E1")
	f.set("A1", "3")
	if want := []call{{"D1", "2", "3"}, {"E1", "-20", "30"}}; !slices.Equal(calls, want) {
		t.Errorf("watch calls = %v; want %v", calls, want)
	}
	calls = nil
	f.set("A1", "-1")
	if want := []call{{"D1", "3", "-1"}, {"E1", "30", "10"}}; !slices.Equal(calls, want) {
		t.Errorf("watch calls = %v; want %v", calls, want)
	}
}

func TestRedefineFormula(t *testing.T) {
	f := newFixture(t)
	f.apply("A1", "1", "A2", "5",
		"B1", `=T("B1", A1+1)`,
		"C1", `=T("C1", B1*2)`)
	got := f.evals(func() { f.set("B1", `=T("B1", A2-3)`) })
	f.expectEvals("same value from a new formula", got, counter{"B1": 1})
	f.expectEvals("change of the old reference", f.evals(func() { f.set("A1", "50") }), counter{})
	f.expectEvals("change of the new reference", f.evals(func() { f.set("A2", "6") }), counter{"B1": 1, "C1": 1})
	f.expect("C1", "6")
	f.expectEvals("the same formula again", f.evals(func() { f.set("B1", `=T("B1", A2-3)`) }), counter{"B1": 1})
	f.expectEvals("formula to constant", f.evals(func() { f.set("B1", "3") }), counter{})
	f.expectEvals("constant to other constant", f.evals(func() { f.set("B1", "4") }), counter{"C1": 1})
	f.expectEvals("change of the reference of the old formula", f.evals(func() { f.set("A2", "9") }), counter{})
	f.expect("C1", "8")
	f.expectEvals("clear B1", f.evals(func() { f.set("B1", "") }), counter{"C1": 1})
	f.expect("C1", "0")
}

func TestRangeReads(t *testing.T) {
	f := newFixture(t)
	var edits []string
	for i := 1; i <= 1000; i++ {
		edits = append(edits, fmt.Sprintf("A%d", i), fmt.Sprint(i))
	}
	edits = append(edits, "B1", `=T("B1", SUM(A1:A1000))`, "B2", `=T("B2", MAX(A1:A10))`)
	f.apply(edits...)
	f.expect("B1", "500500")
	f.expectEvals("Set(A500, 0)", f.evals(func() { f.set("A500", "0") }), counter{"B1": 1})
	f.expectEvals("Set(A5, 6)", f.evals(func() { f.set("A5", "6") }), counter{"B1": 1, "B2": 1})
	f.expect("B1", "500001")
	f.expectEvals("Set(A1001, 1)", f.evals(func() { f.set("A1001", "1") }), counter{})
}

func TestDeepChain(t *testing.T) {
	f := newFixture(t)
	const n = 5000
	edits := []engine.Edit{{Cell: "A1", Input: "0"}}
	for i := 2; i <= n; i++ {
		edits = append(edits, engine.Edit{Cell: fmt.Sprintf("A%d", i), Input: fmt.Sprintf(`=T("x", A%d+1)`, i-1)})
	}
	if err := f.s.Apply(edits); err != nil {
		t.Fatal(err)
	}
	f.expect(fmt.Sprintf("A%d", n), fmt.Sprint(n-1))
	f.expectEvals("Set(A1, 1)", f.evals(func() { f.set("A1", "1") }), counter{"x": n - 1})
	f.expect(fmt.Sprintf("A%d", n), fmt.Sprint(n))
	f.expectEvals("Set(A4000, 0)", f.evals(func() { f.set("A4000", "0") }), counter{"x": n - 4000})
	f.expect(fmt.Sprintf("A%d", n), fmt.Sprint(n-4000))
}

func TestCostDoesNotGrowWithSheet(t *testing.T) {
	f := newFixture(t)
	const n = 100000
	edits := make([]engine.Edit, 0, 2*n+2)
	for i := 1; i <= n; i++ {
		edits = append(edits,
			engine.Edit{Cell: fmt.Sprintf("A%d", i), Input: fmt.Sprint(i)},
			engine.Edit{Cell: fmt.Sprintf("B%d", i), Input: fmt.Sprintf("=A%d*2", i)})
	}
	edits = append(edits, engine.Edit{Cell: "Z1", Input: "0"}, engine.Edit{Cell: "Z2", Input: `=T("Z2", Z1+1)`})
	if err := f.s.Apply(edits); err != nil {
		t.Fatal(err)
	}
	const updates = 20000
	start := time.Now()
	got := f.evals(func() {
		for i := 1; i <= updates; i++ {
			if err := f.s.Set("Z1", fmt.Sprint(i)); err != nil {
				t.Fatal(err)
			}
		}
	})
	elapsed := time.Since(start)
	f.expectEvals("updates of Z1", got, counter{"Z2": updates})
	f.expect("Z2", fmt.Sprint(updates+1))
	f.expect("B777", "1554")
	// The reference engine needs less than 0.2 s for these updates. An
	// engine that visits each cell of the sheet in each update needs more
	// than a minute.
	if elapsed > 20*time.Second {
		t.Errorf("%d updates of one cell in a sheet of %d cells took %v", updates, 2*n, elapsed)
	}
	if !strings.HasPrefix(f.s.Input("B5"), "=") {
		t.Errorf("Input(B5) = %q", f.s.Input("B5"))
	}
}

func TestWholeColumnRanges(t *testing.T) {
	f := newFixture(t)
	var edits []engine.Edit
	add := func(cell, input string) { edits = append(edits, engine.Edit{Cell: cell, Input: input}) }
	for i := 1; i <= 300; i++ {
		add(fmt.Sprintf("A%d", i*7), fmt.Sprint(i))
	}
	for i := 1; i <= 100; i++ {
		add(fmt.Sprintf("%c%d", 'D'+i%3, i*11), fmt.Sprint(i*2))
	}
	for i := 1; i <= 60; i++ {
		add(fmt.Sprintf("G%d", i), fmt.Sprintf(`=T("G", SUM(A1:A1048576)+%d)`, i))
		add(fmt.Sprintf("H%d", i), `=T("H", MAX(D1:F1048576))`)
	}
	for i := 1; i <= 20; i++ {
		add(fmt.Sprintf("I%d", i), `=T("I", COUNT(A1:F200000))`)
	}
	add("J1", `=T("J1", AVERAGE(A1:A1048576))`)
	add("J2", `=T("J2", MIN(A2:A1048576) + COUNT(K1:XFD1048576))`)
	if err := f.s.Apply(edits); err != nil {
		t.Fatal(err)
	}
	f.expect("G1", "45151")
	f.expect("G60", "45210")
	f.expect("H7", "200")
	f.expect("I20", "400")
	f.expect("J1", "150.5")
	f.expect("J2", "1")

	f.expectEvals("Set(A5, 1000)", f.evals(func() { f.set("A5", "1000") }), counter{"G": 60, "I": 20, "J1": 1, "J2": 1})
	f.expect("G2", "46152")
	f.expectEvals("Set(E3, 999)", f.evals(func() { f.set("E3", "999") }), counter{"H": 60, "I": 20})
	f.expect("H60", "999")
	f.expectEvals("Set(A1048576, 1)", f.evals(func() { f.set("A1048576", "1") }), counter{"G": 60, "J1": 1, "J2": 1})
	f.expectEvals("Set(F900000, 1)", f.evals(func() { f.set("F900000", "1") }), counter{"H": 60})
	f.expectEvals("Set(B5, 1)", f.evals(func() { f.set("B5", "1") }), counter{"I": 20})
	f.expectEvals("Set(C1048576, x)", f.evals(func() { f.set("C1048576", "x") }), counter{})
	f.expectEvals("Set(Z77, 5)", f.evals(func() { f.set("Z77", "5") }), counter{"J2": 1})
	f.expect("J2", "2")
	for i := 0; i < 200; i++ {
		f.set("A5", fmt.Sprint(i))
	}
	f.expect("G1", fmt.Sprint(45150+199+1+1))

	if err := f.s.Set("A9999", "=G1"); !errors.Is(err, engine.ErrCycle) {
		t.Errorf("Set(A9999, =G1) = %v; want ErrCycle", err)
	}
	if err := f.s.Set("K1", "=SUM(K2:K1048576)"); err != nil {
		t.Fatal(err)
	}
	if err := f.s.Set("K500000", "=K1"); !errors.Is(err, engine.ErrCycle) {
		t.Errorf("Set(K500000, =K1) = %v; want ErrCycle", err)
	}
	if err := f.s.Set("XFD1048576", "=J2"); !errors.Is(err, engine.ErrCycle) {
		t.Errorf("Set(XFD1048576, =J2) = %v; want ErrCycle", err)
	}
}

func TestRangeErrorsAndOrder(t *testing.T) {
	f := newFixture(t)
	f.apply("B9", "=1/0", "C2", `="x"&D1`, "B1000000", "2",
		"A1", "=SUM(B1:C1048576)",
		"A2", "=COUNT(B1:C1048576)",
		"A3", "=SUM(B10:C1048576)")
	f.expect("A1", value.ErrDivZero)
	f.expect("A2", value.ErrDivZero)
	f.expect("A3", "2")
	f.set("C2", "=SQRTX(1)")
	f.expect("A1", value.ErrName)
	f.set("C2", "3")
	f.expect("A1", value.ErrDivZero)
	f.set("B9", "4")
	f.expect("A1", "9")
	f.expect("A2", "3")
}
