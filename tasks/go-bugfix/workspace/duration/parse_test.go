package duration

import (
	"testing"
	"time"
)

func TestParse(t *testing.T) {
	tests := []struct {
		in   string
		want time.Duration
	}{
		{"1h30m", 90 * time.Minute},
		{"45s", 45 * time.Second},
		{"1.5h", 90 * time.Minute},
		{"2m0.25s", 2*time.Minute + 250*time.Millisecond},
		{"2d12h", 60 * time.Hour},
	}
	for _, tt := range tests {
		got, err := Parse(tt.in)
		if err != nil || got != tt.want {
			t.Errorf("Parse(%q) = %v, %v; want %v", tt.in, got, err, tt.want)
		}
	}
}

func TestParseErrors(t *testing.T) {
	for _, in := range []string{"", "h", "5", "1x", "30m1h", "1h2h"} {
		if _, err := Parse(in); err == nil {
			t.Errorf("Parse(%q): no error", in)
		}
	}
}

func TestFormat(t *testing.T) {
	if got := Format(90 * time.Minute); got != "1h30m" {
		t.Errorf("Format(90m) = %q", got)
	}
}
