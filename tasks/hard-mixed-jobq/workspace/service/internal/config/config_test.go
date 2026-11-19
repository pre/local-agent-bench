package config

import "testing"

func env(values map[string]string) func(string) string {
	return func(name string) string { return values[name] }
}

func TestDefaults(t *testing.T) {
	cfg, err := FromEnv(env(nil))
	if err != nil {
		t.Fatal(err)
	}
	if cfg != Defaults() {
		t.Fatalf("got %+v, want %+v", cfg, Defaults())
	}
}

func TestValues(t *testing.T) {
	cfg, err := FromEnv(env(map[string]string{
		"JOBQ_PORT":                "9000",
		"JOBQ_MAX_TIMEOUT_SECONDS": "60",
		"JOBQ_QUEUE_LIMIT":         "5",
	}))
	if err != nil {
		t.Fatal(err)
	}
	want := Config{Port: 9000, MaxTimeoutSeconds: 60, QueueLimit: 5}
	if cfg != want {
		t.Fatalf("got %+v, want %+v", cfg, want)
	}
}

func TestBadValues(t *testing.T) {
	for _, tc := range []map[string]string{
		{"JOBQ_PORT": "http"},
		{"JOBQ_PORT": "0"},
		{"JOBQ_MAX_TIMEOUT_SECONDS": "-1"},
		{"JOBQ_QUEUE_LIMIT": "1.5"},
	} {
		if _, err := FromEnv(env(tc)); err == nil {
			t.Errorf("%v: no error", tc)
		}
	}
}
