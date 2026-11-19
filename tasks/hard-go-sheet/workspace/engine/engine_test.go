package engine

import (
	"errors"
	"fmt"
	"slices"
	"testing"

	"example.com/sheet/value"
)

func mustSet(t *testing.T, s *Sheet, cell, input string) {
	t.Helper()
	if err := s.Set(cell, input); err != nil {
		t.Fatalf("Set(%s, %q): %v", cell, input, err)
	}
}

func expect(t *testing.T, s *Sheet, cell, want string) {
	t.Helper()
	if got := s.Value(cell).String(); got != want {
		t.Errorf("%s = %q; want %q", cell, got, want)
	}
}

func TestConstants(t *testing.T) {
	s := New()
	mustSet(t, s, "A1", "42")
	mustSet(t, s, "A2", " 2.5e1 ")
	mustSet(t, s, "A3", "true")
	mustSet(t, s, "A4", "hello")
	mustSet(t, s, "A5", "'12")
	mustSet(t, s, "A6", "inf")
	expect(t, s, "A1", "42")
	expect(t, s, "A2", "25")
	expect(t, s, "A3", "TRUE")
	expect(t, s, "A4", "hello")
	expect(t, s, "A5", "12")
	if k := s.Value("A5").Kind(); k != value.KindText {
		t.Errorf("A5 kind = %v; want text", k)
	}
	if k := s.Value("A6").Kind(); k != value.KindText {
		t.Errorf("A6 kind = %v; want text", k)
	}
}

func TestChain(t *testing.T) {
	s := New()
	mustSet(t, s, "A1", "1")
	mustSet(t, s, "A2", "=A1+1")
	mustSet(t, s, "A3", "=A2*10")
	expect(t, s, "A3", "20")
	mustSet(t, s, "A1", "5")
	expect(t, s, "A2", "6")
	expect(t, s, "A3", "60")
}

func TestFormulaBeforeInput(t *testing.T) {
	s := New()
	mustSet(t, s, "B1", "=A1*2")
	expect(t, s, "B1", "0")
	mustSet(t, s, "A1", "4")
	expect(t, s, "B1", "8")
	mustSet(t, s, "A1", "")
	expect(t, s, "B1", "0")
	if s.Input("A1") != "" || slices.Contains(s.Cells(), "A1") {
		t.Error("A1 must be empty after Set(A1, \"\")")
	}
}

func TestIfAndSum(t *testing.T) {
	s := New()
	for i := 1; i <= 5; i++ {
		mustSet(t, s, fmt.Sprintf("A%d", i), fmt.Sprint(i))
	}
	mustSet(t, s, "B1", "=SUM(A1:A5)")
	mustSet(t, s, "B2", `=IF(B1>10, "big", "small")`)
	expect(t, s, "B1", "15")
	expect(t, s, "B2", "big")
	mustSet(t, s, "A5", "-5")
	expect(t, s, "B1", "5")
	expect(t, s, "B2", "small")
}

func TestErrors(t *testing.T) {
	s := New()
	mustSet(t, s, "A1", "0")
	mustSet(t, s, "B1", "=10/A1")
	expect(t, s, "B1", value.ErrDivZero)
	mustSet(t, s, "C1", "=B1+1")
	expect(t, s, "C1", value.ErrDivZero)
	if err := s.Set("C2", "=1+"); !errors.Is(err, ErrSyntax) {
		t.Errorf("syntax error = %v", err)
	}
	if err := s.Set("C0", "1"); !errors.Is(err, ErrAddress) {
		t.Errorf("address error = %v", err)
	}
}

func TestCycle(t *testing.T) {
	s := New()
	mustSet(t, s, "A1", "=B1+1")
	mustSet(t, s, "B1", "=C1+1")
	if err := s.Set("C1", "=A1"); !errors.Is(err, ErrCycle) {
		t.Fatalf("Set(C1, =A1) = %v; want ErrCycle", err)
	}
	if err := s.Set("D1", "=SUM(D1:D3)"); !errors.Is(err, ErrCycle) {
		t.Fatalf("Set(D1, =SUM(D1:D3)) = %v; want ErrCycle", err)
	}
	if s.Input("C1") != "" || s.Input("D1") != "" {
		t.Error("a rejected formula must not change the sheet")
	}
	expect(t, s, "A1", "2")
}

func TestWatch(t *testing.T) {
	s := New()
	var got []string
	if err := s.Watch("B1", func(cell string, old, new value.Value) {
		got = append(got, fmt.Sprintf("%s:%v->%v", cell, old, new))
	}); err != nil {
		t.Fatal(err)
	}
	mustSet(t, s, "A1", "1")
	mustSet(t, s, "B1", "=A1*3")
	mustSet(t, s, "A1", "2")
	mustSet(t, s, "A1", "2")
	want := []string{"B1:->3", "B1:3->6"}
	if !slices.Equal(got, want) {
		t.Errorf("watch calls = %v; want %v", got, want)
	}
}

func TestCustomFunction(t *testing.T) {
	s := New()
	if err := s.RegisterFunc("DOUBLE", func(args []value.Value) value.Value {
		return value.Number(2 * args[0].Num())
	}); err != nil {
		t.Fatal(err)
	}
	for _, bad := range []string{"SUM", "A1", "lower", "", "TRUE", "X-Y"} {
		if err := s.RegisterFunc(bad, nil); !errors.Is(err, ErrFuncName) {
			t.Errorf("RegisterFunc(%q) = %v; want ErrFuncName", bad, err)
		}
	}
	mustSet(t, s, "A1", "21")
	mustSet(t, s, "A2", "=double(A1)")
	expect(t, s, "A2", "42")
}

func TestApply(t *testing.T) {
	s := New()
	err := s.Apply([]Edit{{"A1", "1"}, {"A2", "=A1+A3"}, {"A3", "10"}})
	if err != nil {
		t.Fatal(err)
	}
	expect(t, s, "A2", "11")
	if got := s.Cells(); !slices.Equal(got, []string{"A1", "A2", "A3"}) {
		t.Errorf("Cells = %v", got)
	}
}
