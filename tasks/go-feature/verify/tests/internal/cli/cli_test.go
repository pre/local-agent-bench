package cli

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

const fleet = `# test fleet
n-c01 rack=r03 state=ready   gpus=8 used=1 model=mi300x
n-a01 rack=r01 state=ready   gpus=8 used=3 model=mi300x
n-a02 rack=r01 state=drained gpus=8 used=2
n-b01 rack=r02 state=down    gpus=4 used=0 model=mi250
n-a03 rack=r01 state=ready   gpus=8 used=8 model=mi300x
n-c02 rack=r03 state=drained gpus=8 used=0 model=mi300x
n-b02 rack=r02 state=ready   gpus=4 used=1 model=mi250
n-c03 rack=r03 state=ready   gpus=8 used=0 model=mi300x
`

func writeInventory(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "nodes.inv")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func run(t *testing.T, args ...string) (string, string, int) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := Run(args, &stdout, &stderr)
	return stdout.String(), stderr.String(), code
}

// fields splits the output into lines and the lines into fields, so the
// comparison does not depend on the column padding.
func fields(out string) [][]string {
	var rows [][]string
	for _, line := range strings.Split(strings.TrimRight(out, "\n"), "\n") {
		rows = append(rows, strings.Fields(line))
	}
	return rows
}

func rows(lines ...string) [][]string {
	return fields(strings.Join(lines, "\n"))
}

func mustRun(t *testing.T, args ...string) string {
	t.Helper()
	out, errOut, code := run(t, args...)
	if code != 0 {
		t.Fatalf("Run(%q) = %d, stderr: %s", args, code, errOut)
	}
	return out
}

func TestTableOutput(t *testing.T) {
	path := writeInventory(t, fleet)
	got := fields(mustRun(t, "-f", path, "-rack", "r02"))
	want := rows(
		"NAME RACK STATE GPUS USED MODEL",
		"n-b01 r02 down 4 0 mi250",
		"n-b02 r02 ready 4 1 mi250",
	)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %q, want %q", got, want)
	}
	got = fields(mustRun(t, "-f", path, "-state", "drained"))
	want = rows(
		"NAME RACK STATE GPUS USED MODEL",
		"n-a02 r01 drained 8 2 -",
		"n-c02 r03 drained 8 0 mi300x",
	)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestJSONOutput(t *testing.T) {
	path := writeInventory(t, fleet)
	out := mustRun(t, "-f", path, "-o", "json", "-state", "down")
	var got []map[string]any
	if err := json.Unmarshal([]byte(out), &got); err != nil {
		t.Fatalf("invalid JSON %q: %v", out, err)
	}
	want := []map[string]any{{"name": "n-b01", "rack": "r02", "state": "down", "gpus": 4.0, "used": 0.0, "model": "mi250"}}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %v, want %v", got, want)
	}
	out = mustRun(t, "-f", path, "-o", "json", "-rack", "r09")
	if strings.TrimSpace(out) != "[]" {
		t.Errorf("no match: got %q, want []", out)
	}
}

func TestErrors(t *testing.T) {
	path := writeInventory(t, fleet)
	for _, args := range [][]string{
		{},
		{"-f", path, "-state", "busy"},
		{"-f", path, "-o", "yaml"},
		{"-f", path, "extra"},
	} {
		if _, _, code := run(t, args...); code != 2 {
			t.Errorf("Run(%q) = %d, want 2", args, code)
		}
	}
	if _, _, code := run(t, "-f", filepath.Join(t.TempDir(), "missing.inv")); code != 1 {
		t.Errorf("missing file: code %d, want 1", code)
	}
	bad := writeInventory(t, "n1 rack=r1 state=ready gpus=2 used=3\n")
	if _, _, code := run(t, "-f", bad); code != 1 {
		t.Errorf("used > gpus: code %d, want 1", code)
	}
}

func TestByRackTable(t *testing.T) {
	path := writeInventory(t, fleet)
	got := fields(mustRun(t, "-f", path, "-by-rack"))
	want := rows(
		"RACK NODES READY GPUS FREE",
		"r01 3 2 24 5",
		"r02 2 1 8 3",
		"r03 3 2 24 15",
		"TOTAL 8 5 56 23",
	)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %q, want %q", got, want)
	}
}

func decodeRacks(t *testing.T, out string) []map[string]any {
	t.Helper()
	var got []map[string]any
	if err := json.Unmarshal([]byte(out), &got); err != nil {
		t.Fatalf("invalid JSON %q: %v", out, err)
	}
	return got
}

func rack(name string, nodes, ready, gpus, free int) map[string]any {
	return map[string]any{
		"rack":  name,
		"nodes": float64(nodes),
		"ready": float64(ready),
		"gpus":  float64(gpus),
		"free":  float64(free),
	}
}

func TestByRackJSON(t *testing.T) {
	path := writeInventory(t, fleet)
	got := decodeRacks(t, mustRun(t, "-f", path, "-by-rack", "-o", "json"))
	want := []map[string]any{
		rack("r01", 3, 2, 24, 5),
		rack("r02", 2, 1, 8, 3),
		rack("r03", 3, 2, 24, 15),
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %v, want %v", got, want)
	}
}

func TestByRackFreeCountsOnlyReadyNodes(t *testing.T) {
	path := writeInventory(t, `
x1 rack=r07 state=drained gpus=8 used=1
x2 rack=r07 state=down gpus=8 used=0
x3 rack=r07 state=ready gpus=8 used=6
x4 rack=r05 state=ready gpus=4 used=4
`)
	got := fields(mustRun(t, "-f", path, "-by-rack"))
	want := rows(
		"RACK NODES READY GPUS FREE",
		"r05 1 1 4 0",
		"r07 3 1 24 2",
		"TOTAL 4 2 28 2",
	)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestByRackWithFilters(t *testing.T) {
	path := writeInventory(t, fleet)
	got := fields(mustRun(t, "-f", path, "-by-rack", "-state", "drained"))
	want := rows(
		"RACK NODES READY GPUS FREE",
		"r01 1 0 8 0",
		"r03 1 0 8 0",
		"TOTAL 2 0 16 0",
	)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("-state drained: got %q, want %q", got, want)
	}
	gotJSON := decodeRacks(t, mustRun(t, "-by-rack", "-f", path, "-rack", "r03", "-o", "json"))
	wantJSON := []map[string]any{rack("r03", 3, 2, 24, 15)}
	if !reflect.DeepEqual(gotJSON, wantJSON) {
		t.Errorf("-rack r03: got %v, want %v", gotJSON, wantJSON)
	}
}

func TestByRackNoMatch(t *testing.T) {
	path := writeInventory(t, fleet)
	got := fields(mustRun(t, "-f", path, "-by-rack", "-rack", "r42"))
	want := rows(
		"RACK NODES READY GPUS FREE",
		"TOTAL 0 0 0 0",
	)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %q, want %q", got, want)
	}
	out := mustRun(t, "-f", path, "-by-rack", "-rack", "r42", "-o", "json")
	if strings.TrimSpace(out) != "[]" {
		t.Errorf("JSON: got %q, want []", out)
	}
}
