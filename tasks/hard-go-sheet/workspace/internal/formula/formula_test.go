package formula

import (
	"errors"
	"testing"
)

func TestParsePrecedence(t *testing.T) {
	e, err := Parse("1+2*3^2^1")
	if err != nil {
		t.Fatal(err)
	}
	b, ok := e.(*Binary)
	if !ok || b.Op != "+" {
		t.Fatalf("top = %#v", e)
	}
	mul, ok := b.R.(*Binary)
	if !ok || mul.Op != "*" {
		t.Fatalf("right = %#v", b.R)
	}
	pow, ok := mul.R.(*Binary)
	if !ok || pow.Op != "^" {
		t.Fatalf("power = %#v", mul.R)
	}
	if _, ok := pow.R.(*Binary); !ok {
		t.Fatalf("^ must be right associative: %#v", pow)
	}
}

func TestParseCallAndRange(t *testing.T) {
	e, err := Parse(`sum(A1:B2, 3) & "x""y"`)
	if err != nil {
		t.Fatal(err)
	}
	cat := e.(*Binary)
	call := cat.L.(*Call)
	if call.Name != "SUM" || len(call.Args) != 2 {
		t.Fatalf("call = %#v", call)
	}
	if r := call.Args[0].(*RangeRef); r.Range.Size() != 4 {
		t.Fatalf("range = %v", r.Range)
	}
	if s := cat.R.(*TextLit); s.Val != `x"y` {
		t.Fatalf("text = %q", s.Val)
	}
}

func TestParseErrors(t *testing.T) {
	for _, src := range []string{"", "1+", "(1", "A1:B2", "A1:B2+1", "SUM(1,", `"abc`, "1 2", "FOO", "A1:", "#"} {
		if _, err := Parse(src); !errors.Is(err, ErrSyntax) {
			t.Errorf("Parse(%q) error = %v; want ErrSyntax", src, err)
		}
	}
}

func TestRefs(t *testing.T) {
	e, err := Parse("IF(A1>0, SUM(B1:B3), A1+C9)")
	if err != nil {
		t.Fatal(err)
	}
	var got []string
	for _, a := range Refs(e) {
		got = append(got, a.String())
	}
	want := []string{"A1", "B1", "B2", "B3", "C9"}
	if len(got) != len(want) {
		t.Fatalf("Refs = %v; want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("Refs = %v; want %v", got, want)
		}
	}
}
