package addr

import (
	"errors"
	"testing"
)

func TestParse(t *testing.T) {
	cases := map[string]Addr{
		"A1":         {1, 1},
		"b7":         {2, 7},
		"Z10":        {26, 10},
		"AA1":        {27, 1},
		"XFD1048576": {MaxCol, MaxRow},
	}
	for in, want := range cases {
		got, err := Parse(in)
		if err != nil || got != want {
			t.Errorf("Parse(%q) = %v, %v; want %v", in, got, err, want)
		}
	}
	for _, in := range []string{"", "A", "1", "A0", "A01", "$A$1", "XFE1", "A1048577", "A1B"} {
		if _, err := Parse(in); !errors.Is(err, ErrAddress) {
			t.Errorf("Parse(%q) error = %v; want ErrAddress", in, err)
		}
	}
}

func TestStringRoundTrip(t *testing.T) {
	for _, s := range []string{"A1", "Z9", "AA10", "AZ3", "BA4", "ZZ5", "AAA6", "XFD7"} {
		if got := MustParse(s).String(); got != s {
			t.Errorf("String of %q = %q", s, got)
		}
	}
}

func TestRange(t *testing.T) {
	r, err := ParseRange("B3:A1")
	if err != nil {
		t.Fatal(err)
	}
	if r.String() != "A1:B3" || r.Size() != 6 {
		t.Fatalf("range = %v, size %d", r, r.Size())
	}
	cells := r.Cells()
	if cells[0] != MustParse("A1") || cells[1] != MustParse("B1") || cells[5] != MustParse("B3") {
		t.Errorf("cells = %v", cells)
	}
	if !r.Contains(MustParse("B2")) || r.Contains(MustParse("C2")) {
		t.Error("Contains is wrong")
	}
}

func TestLess(t *testing.T) {
	if !Less(MustParse("Z1"), MustParse("A2")) || Less(MustParse("B2"), MustParse("A2")) {
		t.Error("Less must order by row, then by column")
	}
}
