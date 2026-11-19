package cli

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
)

func run(t *testing.T, args ...string) (string, string, int) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := Main(args, &stdout, &stderr)
	return stdout.String(), stderr.String(), code
}

func mustRun(t *testing.T, args ...string) string {
	t.Helper()
	out, errOut, code := run(t, args...)
	if code != 0 {
		t.Fatalf("Main(%q) = %d, stderr:\n%s", args, code, errOut)
	}
	return out
}

func testdata(name string) string {
	return filepath.Join("..", "..", "testdata", name)
}

func writeJSON(t *testing.T, name string, v any) string {
	t.Helper()
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

type testNode struct {
	Name   string            `json:"name"`
	Rack   string            `json:"rack"`
	Labels map[string]string `json:"labels,omitempty"`
	Health string            `json:"health,omitempty"`
}

type testInventory struct {
	Cluster string     `json:"cluster"`
	Nodes   []testNode `json:"nodes"`
}

func TestVersion(t *testing.T) {
	if out := mustRun(t, "version"); !strings.HasPrefix(out, "rollout ") {
		t.Errorf("got %q", out)
	}
}

func TestCheck(t *testing.T) {
	out := mustRun(t, "check", "-inventory", testdata("fleet-b.json"), "-policy", testdata("policy-canary.json"))
	want := "inventory: 18 nodes in 4 racks\npolicy: batches of 4 nodes, 1 per rack, 2 canaries\n"
	if out != want {
		t.Errorf("got %q, want %q", out, want)
	}
}

func TestPlanWithoutCanary(t *testing.T) {
	out := mustRun(t, "plan", "-inventory", testdata("fleet-b.json"), "-policy", testdata("policy-gpu.json"))
	want := `cluster build-b: 12 nodes in 4 batches
batch 1: gpu-b01 gpu-b05 gpu-b09 gpu-b12
batch 2: gpu-b02 gpu-b07 gpu-b10 gpu-b13
batch 3: gpu-b03 gpu-b08 gpu-b11
batch 4: gpu-b04
skipped (health check failed): gpu-b06
`
	if out != want {
		t.Errorf("got:\n%s\nwant:\n%s", out, want)
	}
}

func TestPlanCanaryFleetB(t *testing.T) {
	out := mustRun(t, "plan", "-inventory", testdata("fleet-b.json"), "-policy", testdata("policy-canary.json"))
	want := `cluster build-b: 12 nodes in 4 batches
batch 1 (canary): gpu-b03 gpu-b07
batch 2: gpu-b01 gpu-b05 gpu-b09 gpu-b12
batch 3: gpu-b02 gpu-b08 gpu-b10 gpu-b13
batch 4: gpu-b04 gpu-b11
skipped (health check failed): gpu-b06
`
	if out != want {
		t.Errorf("got:\n%s\nwant:\n%s", out, want)
	}
}

type jsonPlan struct {
	Cluster string `json:"cluster"`
	Batches []struct {
		Canary bool     `json:"canary"`
		Nodes  []string `json:"nodes"`
	} `json:"batches"`
	Skipped []string `json:"skipped"`
}

func TestPlanCanaryJSON(t *testing.T) {
	out := mustRun(t, "plan", "-inventory", testdata("fleet-b.json"), "-policy", testdata("policy-canary.json"), "-o", "json")
	var got jsonPlan
	if err := json.Unmarshal([]byte(out), &got); err != nil {
		t.Fatalf("invalid JSON: %v\n%s", err, out)
	}
	want := [][]string{
		{"gpu-b03", "gpu-b07"},
		{"gpu-b01", "gpu-b05", "gpu-b09", "gpu-b12"},
		{"gpu-b02", "gpu-b08", "gpu-b10", "gpu-b13"},
		{"gpu-b04", "gpu-b11"},
	}
	if len(got.Batches) != len(want) {
		t.Fatalf("got %d batches, want %d:\n%s", len(got.Batches), len(want), out)
	}
	for i, b := range got.Batches {
		if b.Canary != (i == 0) || !reflect.DeepEqual(b.Nodes, want[i]) {
			t.Errorf("batch %d: got %+v, want canary=%v %v", i+1, b, i == 0, want[i])
		}
	}
	if got.Cluster != "build-b" || !reflect.DeepEqual(got.Skipped, []string{"gpu-b06"}) {
		t.Errorf("got cluster %q skipped %v", got.Cluster, got.Skipped)
	}
}

func canaryPolicy(t *testing.T, count, batch, perRack int) string {
	t.Helper()
	return writeJSON(t, "policy.json", map[string]any{
		"selector":              "pool=gpu",
		"exclude":               "role=control",
		"canary":                map[string]any{"selector": "canary=true", "count": count},
		"maxBatchSize":          batch,
		"maxUnavailablePerRack": perRack,
	})
}

func TestPlanCanaryOtherFleet(t *testing.T) {
	inv := testInventory{Cluster: "lab", Nodes: []testNode{
		{Name: "m-ctl", Rack: "ra", Labels: map[string]string{"role": "control", "pool": "gpu", "canary": "true"}},
		{Name: "m-09", Rack: "rc", Labels: map[string]string{"pool": "gpu"}},
		{Name: "m-01", Rack: "ra", Labels: map[string]string{"pool": "gpu", "canary": "true"}},
		{Name: "m-05", Rack: "rb", Labels: map[string]string{"pool": "gpu"}},
		{Name: "m-02", Rack: "ra", Labels: map[string]string{"pool": "gpu"}},
		{Name: "x-01", Rack: "rb", Labels: map[string]string{"pool": "cpu", "canary": "true"}},
		{Name: "m-06", Rack: "rb", Labels: map[string]string{"pool": "gpu", "canary": "true"}, Health: "failed"},
		{Name: "m-03", Rack: "ra", Labels: map[string]string{"pool": "gpu"}},
		{Name: "m-07", Rack: "rb", Labels: map[string]string{"pool": "gpu", "canary": "true"}},
		{Name: "m-10", Rack: "rc", Labels: map[string]string{"pool": "gpu", "canary": "true"}},
		{Name: "m-08", Rack: "rb", Labels: map[string]string{"pool": "gpu"}},
		{Name: "m-04", Rack: "ra", Labels: map[string]string{"pool": "gpu"}, Health: "degraded"},
	}}
	invPath := writeJSON(t, "inv.json", inv)
	out := mustRun(t, "plan", "-inventory", invPath, "-policy", canaryPolicy(t, 3, 3, 2))
	want := `cluster lab: 9 nodes in 3 batches
batch 1 (canary): m-01 m-07 m-10
batch 2: m-02 m-03 m-05
batch 3: m-04 m-08 m-09
skipped (health check failed): m-06
`
	if out != want {
		t.Errorf("got:\n%s\nwant:\n%s", out, want)
	}
}

func TestPlanNoCanaryCandidate(t *testing.T) {
	inv := testInventory{Cluster: "lab", Nodes: []testNode{
		{Name: "n-1", Rack: "r1", Labels: map[string]string{"pool": "gpu"}},
		{Name: "n-2", Rack: "r2", Labels: map[string]string{"pool": "gpu"}},
		{Name: "c-1", Rack: "r1", Labels: map[string]string{"pool": "cpu", "canary": "true"}},
		{Name: "n-3", Rack: "r1", Labels: map[string]string{"pool": "gpu", "canary": "true"}, Health: "failed"},
		{Name: "n-4", Rack: "r2", Labels: map[string]string{"pool": "gpu"}},
	}}
	invPath := writeJSON(t, "inv.json", inv)
	out := mustRun(t, "plan", "-inventory", invPath, "-policy", canaryPolicy(t, 1, 2, 1))
	want := `cluster lab: 3 nodes in 2 batches
batch 1: n-1 n-2
batch 2: n-4
skipped (health check failed): n-3
`
	if out != want {
		t.Errorf("got:\n%s\nwant:\n%s", out, want)
	}
}

// lcg is a small deterministic number generator for the generated fleets.
type lcg uint64

func (g *lcg) next(n int) int {
	*g = *g*6364136223846793005 + 1442695040888963407
	return int((uint64(*g) >> 33) % uint64(n))
}

func TestPlanEveryNodeOnce(t *testing.T) {
	for seed := 1; seed <= 25; seed++ {
		g := lcg(seed)
		var inv testInventory
		inv.Cluster = fmt.Sprintf("gen-%d", seed)
		nodeCount := 8 + g.next(30)
		racks := 1 + g.next(5)
		var eligible, canaries []string
		for i := range nodeCount {
			n := testNode{
				Name:   fmt.Sprintf("node-%03d", g.next(1000)*100+i),
				Rack:   fmt.Sprintf("rack-%d", g.next(racks)),
				Labels: map[string]string{"pool": "gpu"},
			}
			switch g.next(10) {
			case 0:
				n.Labels["pool"] = "cpu"
			case 1:
				n.Labels["role"] = "control"
			case 2:
				n.Health = "failed"
			case 3:
				n.Health = "degraded"
			}
			if g.next(3) == 0 {
				n.Labels["canary"] = "true"
			}
			inv.Nodes = append(inv.Nodes, n)
			ok := n.Labels["pool"] == "gpu" && n.Labels["role"] != "control" && n.Health != "failed"
			if ok {
				eligible = append(eligible, n.Name)
				if n.Labels["canary"] == "true" {
					canaries = append(canaries, n.Name)
				}
			}
		}
		batch := 2 + g.next(5)
		perRack := 1 + g.next(3)
		count := g.next(batch + 1)
		sort.Strings(canaries)
		if len(canaries) > count {
			canaries = canaries[:count]
		}

		invPath := writeJSON(t, "inv.json", inv)
		out, errOut, code := run(t, "plan", "-o", "json", "-inventory", invPath, "-policy", canaryPolicy(t, count, batch, perRack))
		if code != 0 {
			t.Fatalf("seed %d: exit code %d:\n%s", seed, code, errOut)
		}
		var got jsonPlan
		if err := json.Unmarshal([]byte(out), &got); err != nil {
			t.Fatalf("seed %d: invalid JSON: %v", seed, err)
		}
		var planned []string
		for i, b := range got.Batches {
			if b.Canary != (i == 0 && len(canaries) > 0) {
				t.Errorf("seed %d: batch %d canary=%v", seed, i+1, b.Canary)
			}
			if i == 0 && len(canaries) > 0 && !reflect.DeepEqual(b.Nodes, canaries) {
				t.Errorf("seed %d: canaries %v, want %v", seed, b.Nodes, canaries)
			}
			planned = append(planned, b.Nodes...)
		}
		sort.Strings(planned)
		sort.Strings(eligible)
		if !reflect.DeepEqual(planned, eligible) {
			t.Errorf("seed %d: planned nodes %v, want %v", seed, planned, eligible)
		}
	}
}
