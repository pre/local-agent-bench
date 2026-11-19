package policy

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadKeepsDefaults(t *testing.T) {
	path := filepath.Join(t.TempDir(), "p.json")
	os.WriteFile(path, []byte(`{"selector":"pool=gpu","maxBatchSize":6}`), 0o644)
	p, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if p.Selector != "pool=gpu" || p.MaxBatchSize != 6 || p.MaxUnavailablePerRack != 1 || p.Exclude != "role=control" {
		t.Errorf("got %+v", p)
	}
}

func TestLoadErrors(t *testing.T) {
	for _, content := range []string{
		`{"maxBatchSize":0}`,
		`{"maxUnavailablePerRack":0}`,
		`{"canary":{"count":5},"maxBatchSize":4}`,
		`{"canary":{"count":-1}}`,
		`{"selector":"=x"}`,
		`{"batchSize":3}`,
	} {
		path := filepath.Join(t.TempDir(), "p.json")
		os.WriteFile(path, []byte(content), 0o644)
		if _, err := Load(path); err == nil {
			t.Errorf("Load(%s): no error", content)
		}
	}
}
