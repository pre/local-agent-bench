package main

import (
	"bytes"
	"testing"
)

func TestRun(t *testing.T) {
	var out, errOut bytes.Buffer
	if code := run([]string{"1h30m", "45m"}, &out, &errOut); code != 0 {
		t.Fatalf("exit code %d, stderr %q", code, errOut.String())
	}
	if got := out.String(); got != "2h15m\n" {
		t.Errorf("output %q, want %q", got, "2h15m\n")
	}
}
