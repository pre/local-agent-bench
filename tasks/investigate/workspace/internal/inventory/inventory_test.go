package inventory

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func node(name, rack string, labels map[string]string) Node {
	return Node{Name: name, Rack: rack, Labels: labels, Health: HealthOK}
}

func TestSelector(t *testing.T) {
	gpu := node("a", "r1", map[string]string{"pool": "gpu", "canary": "true"})
	cpu := node("b", "r1", map[string]string{"pool": "cpu"})
	tests := []struct {
		text     string
		gpu, cpu bool
	}{
		{"", true, true},
		{"pool=gpu", true, false},
		{"pool!=gpu", false, true},
		{"canary", true, false},
		{"!canary", false, true},
		{"pool=gpu,canary=true", true, false},
		{"pool=cpu, !canary", false, true},
	}
	for _, tt := range tests {
		sel, err := ParseSelector(tt.text)
		if err != nil {
			t.Fatalf("ParseSelector(%q): %v", tt.text, err)
		}
		if got := sel.Matches(gpu); got != tt.gpu {
			t.Errorf("%q matches gpu node: %v", tt.text, got)
		}
		if got := sel.Matches(cpu); got != tt.cpu {
			t.Errorf("%q matches cpu node: %v", tt.text, got)
		}
	}
	if _, err := ParseSelector("pool=gpu,=x"); err == nil {
		t.Error("empty key: no error")
	}
}

func TestSelect(t *testing.T) {
	inv := &Inventory{Nodes: []Node{
		node("a", "r1", map[string]string{"pool": "gpu"}),
		node("b", "r2", map[string]string{"pool": "cpu"}),
		node("c", "r1", map[string]string{"pool": "gpu"}),
	}}
	if got := inv.Racks(); !reflect.DeepEqual(got, []string{"r1", "r2"}) {
		t.Errorf("Racks() = %v", got)
	}
	sel, _ := ParseSelector("pool=gpu")
	if got := Names(inv.Select(sel)); !reflect.DeepEqual(got, []string{"a", "c"}) {
		t.Errorf("got %v", got)
	}
}

func TestLoad(t *testing.T) {
	dir := t.TempDir()
	good := filepath.Join(dir, "good.json")
	os.WriteFile(good, []byte(`{"cluster":"c1","nodes":[{"name":"a","rack":"r1"},{"name":"b","rack":"r1","health":"failed"}]}`), 0o644)
	inv, err := Load(good)
	if err != nil {
		t.Fatal(err)
	}
	if inv.Nodes[0].Health != HealthOK || inv.Nodes[1].Health != HealthFailed {
		t.Errorf("health: %+v", inv.Nodes)
	}
	for _, content := range []string{
		`{"nodes":[{"name":"a"}]}`,
		`{"nodes":[{"rack":"r1"}]}`,
		`{"nodes":[{"name":"a","rack":"r1"},{"name":"a","rack":"r2"}]}`,
		`{"nodes":[{"name":"a","rack":"r1","health":"sick"}]}`,
		`{"nodes":`,
	} {
		bad := filepath.Join(dir, "bad.json")
		os.WriteFile(bad, []byte(content), 0o644)
		if _, err := Load(bad); err == nil {
			t.Errorf("Load(%s): no error", content)
		}
	}
}
