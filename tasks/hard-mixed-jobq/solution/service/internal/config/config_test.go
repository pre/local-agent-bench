package config

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func env(values map[string]string) func(string) string {
	return func(name string) string { return values[name] }
}

func TestDefaults(t *testing.T) {
	cfg, err := FromEnv(env(map[string]string{"JOBQ_TOKEN_FILE": "/t"}))
	if err != nil {
		t.Fatal(err)
	}
	want := Defaults()
	want.TokenFile = "/t"
	if cfg != want {
		t.Fatalf("got %+v, want %+v", cfg, want)
	}
}

func TestValues(t *testing.T) {
	cfg, err := FromEnv(env(map[string]string{
		"JOBQ_API_ADDR":     ":9000",
		"JOBQ_METRICS_ADDR": "127.0.0.1:9001",
		"JOBQ_TOKEN_FILE":   "/t",
		"JOBQ_MAX_TIMEOUT":  "6h",
		"JOBQ_QUEUE_LIMIT":  "5",
		"JOBQ_DRAIN_DELAY":  "0s",
	}))
	if err != nil {
		t.Fatal(err)
	}
	want := Config{APIAddr: ":9000", MetricsAddr: "127.0.0.1:9001", TokenFile: "/t",
		MaxTimeout: 6 * time.Hour, QueueLimit: 5, DrainDelay: 0}
	if cfg != want {
		t.Fatalf("got %+v, want %+v", cfg, want)
	}
}

func TestRefused(t *testing.T) {
	for _, tc := range []map[string]string{
		{},
		{"JOBQ_TOKEN_FILE": "/t", "JOBQ_PORT": "8080"},
		{"JOBQ_TOKEN_FILE": "/t", "JOBQ_MAX_TIMEOUT_SECONDS": "60"},
		{"JOBQ_TOKEN_FILE": "/t", "JOBQ_API_ADDR": "7070"},
		{"JOBQ_TOKEN_FILE": "/t", "JOBQ_MAX_TIMEOUT": "0s"},
		{"JOBQ_TOKEN_FILE": "/t", "JOBQ_MAX_TIMEOUT": "60"},
		{"JOBQ_TOKEN_FILE": "/t", "JOBQ_DRAIN_DELAY": "-1s"},
		{"JOBQ_TOKEN_FILE": "/t", "JOBQ_QUEUE_LIMIT": "0"},
	} {
		if _, err := FromEnv(env(tc)); err == nil {
			t.Errorf("%v: no error", tc)
		}
	}
}

func TestReadToken(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "token")
	os.WriteFile(path, []byte(" abc\n"), 0o600)
	if tok, err := ReadToken(path); err != nil || tok != "abc" {
		t.Fatalf("got %q, %v", tok, err)
	}
	os.WriteFile(path, []byte("\n"), 0o600)
	if _, err := ReadToken(path); err == nil {
		t.Fatal("empty token: no error")
	}
	if _, err := ReadToken(filepath.Join(dir, "missing")); err == nil {
		t.Fatal("missing file: no error")
	}
}
