package cli

import (
	"bytes"
	"path/filepath"
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

func TestVersion(t *testing.T) {
	if out := mustRun(t, "version"); !strings.HasPrefix(out, "rollout ") {
		t.Errorf("got %q", out)
	}
}

func TestUsage(t *testing.T) {
	if _, _, code := run(t); code != 2 {
		t.Errorf("no command: code %d, want 2", code)
	}
	if _, _, code := run(t, "deploy"); code != 2 {
		t.Errorf("unknown command: code %d, want 2", code)
	}
	if _, _, code := run(t, "plan"); code != 1 {
		t.Errorf("plan without -inventory: code %d, want 1", code)
	}
}

func TestPlanFleetA(t *testing.T) {
	out := mustRun(t, "plan", "-inventory", testdata("fleet-a.json"), "-policy", testdata("policy-gpu.json"))
	want := `cluster build-a: 4 nodes in 2 batches
batch 1: gpu-a01 gpu-a03
batch 2: gpu-a02 gpu-a04
skipped (health check failed): gpu-a05
`
	if out != want {
		t.Errorf("got:\n%s\nwant:\n%s", out, want)
	}
}
