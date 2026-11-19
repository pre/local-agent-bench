package inventory

import (
	"reflect"
	"strings"
	"testing"
)

func TestParse(t *testing.T) {
	in := `
# comment
gpu-a01 rack=r01 state=ready gpus=8 used=3 model=mi300x
gpu-a02 rack=r01 state=drained gpus=8
`
	got, err := Parse(strings.NewReader(in))
	if err != nil {
		t.Fatal(err)
	}
	want := []Node{
		{Name: "gpu-a01", Rack: "r01", State: Ready, GPUs: 8, GPUsUsed: 3, Model: "mi300x"},
		{Name: "gpu-a02", Rack: "r01", State: Drained, GPUs: 8},
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %+v, want %+v", got, want)
	}
}

func TestParseErrors(t *testing.T) {
	for _, in := range []string{
		"n1 rack=r1 state=ready",
		"n1 state=ready gpus=8",
		"n1 rack=r1 gpus=8",
		"n1 rack=r1 state=busy gpus=8",
		"n1 rack=r1 state=ready gpus=-1",
		"n1 rack=r1 state=ready gpus=2 used=3",
		"n1 rack=r1 state=ready gpus=2 color=red",
		"n1 rack=r1 state=ready gpus=2\nn1 rack=r2 state=ready gpus=2",
	} {
		if _, err := Parse(strings.NewReader(in)); err == nil {
			t.Errorf("Parse(%q): no error", in)
		}
	}
}

func TestFilter(t *testing.T) {
	nodes := []Node{
		{Name: "a", Rack: "r1", State: Ready},
		{Name: "b", Rack: "r2", State: Ready},
		{Name: "c", Rack: "r1", State: Down},
	}
	got := Filter{Rack: "r1", State: Ready}.Apply(nodes)
	if len(got) != 1 || got[0].Name != "a" {
		t.Errorf("got %+v", got)
	}
	if got := (Filter{}).Apply(nodes); len(got) != 3 {
		t.Errorf("empty filter: got %d nodes", len(got))
	}
}
