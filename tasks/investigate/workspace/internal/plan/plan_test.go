package plan

import (
	"fmt"
	"reflect"
	"testing"

	"example.com/rollout/internal/inventory"
	"example.com/rollout/internal/policy"
)

func nodes(spec ...string) []inventory.Node {
	var out []inventory.Node
	for _, s := range spec {
		var name, rack string
		fmt.Sscanf(s, "%s %s", &name, &rack)
		out = append(out, inventory.Node{Name: name, Rack: rack, Health: inventory.HealthOK})
	}
	return out
}

func batchNames(batches [][]inventory.Node) [][]string {
	var out [][]string
	for _, b := range batches {
		out = append(out, inventory.Names(b))
	}
	return out
}

func TestMakeBatches(t *testing.T) {
	in := nodes("a2 r1", "b1 r2", "a1 r1", "c1 r3", "a3 r1", "b2 r2")
	got := batchNames(makeBatches(in, 2, 1))
	want := [][]string{{"a1", "b1"}, {"a2", "b2"}, {"a3", "c1"}}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %v, want %v", got, want)
	}
	got = batchNames(makeBatches(in, 4, 2))
	want = [][]string{{"a1", "a2", "b1", "b2"}, {"a3", "c1"}}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %v, want %v", got, want)
	}
}

func TestBuildWithoutCanary(t *testing.T) {
	inv := &inventory.Inventory{Cluster: "c", Nodes: nodes("n1 r1", "n2 r1", "n3 r2", "n4 r2")}
	inv.Nodes[3].Health = inventory.HealthFailed
	pol := policy.Default
	p, err := Build(inv, &pol)
	if err != nil {
		t.Fatal(err)
	}
	if err := Validate(p, &pol); err != nil {
		t.Fatal(err)
	}
	if p.NodeCount() != 3 || !reflect.DeepEqual(p.Skipped, []string{"n4"}) {
		t.Errorf("got %+v", p)
	}
}

func TestValidate(t *testing.T) {
	pol := policy.Policy{MaxBatchSize: 2, MaxUnavailablePerRack: 1, Canary: policy.Canary{Count: 1}}
	bad := []*Plan{
		{Batches: []Batch{{Nodes: nodes("a r1", "b r2")}, {Nodes: nodes("a r1")}}},
		{Batches: []Batch{{Nodes: nodes("a r1", "b r2", "c r3")}}},
		{Batches: []Batch{{Nodes: nodes("a r1", "b r1")}}},
		{Batches: []Batch{{Nodes: nodes("a r1")}, {Canary: true, Nodes: nodes("b r1")}}},
		{Batches: []Batch{{Canary: true, Nodes: nodes("a r1", "b r2")}}},
		{Batches: []Batch{{}}},
	}
	for i, p := range bad {
		if err := Validate(p, &pol); err == nil {
			t.Errorf("plan %d: no error", i)
		}
	}
}
