package duration_test

import (
	"testing"
	"time"

	"example.com/dur/duration"
)

const (
	day  = 24 * time.Hour
	week = 7 * day
)

type parseCase struct {
	in   string
	want time.Duration
}

func checkParse(t *testing.T, cases []parseCase) {
	t.Helper()
	for _, c := range cases {
		got, err := duration.Parse(c.in)
		if err != nil || got != c.want {
			t.Errorf("Parse(%q) = %v, %v; want %v", c.in, got, err, c.want)
		}
	}
}

func checkErrors(t *testing.T, inputs []string) {
	t.Helper()
	for _, in := range inputs {
		if got, err := duration.Parse(in); err == nil {
			t.Errorf("Parse(%q) = %v, no error; want an error", in, got)
		}
	}
}

func TestHiddenBasic(t *testing.T) {
	checkParse(t, []parseCase{
		{"1h30m", 90 * time.Minute},
		{"45s", 45 * time.Second},
		{"0s", 0},
		{"007s", 7 * time.Second},
		{"1.5h", 90 * time.Minute},
		{"2m0.25s", 2*time.Minute + 250*time.Millisecond},
		{"2d12h", 60 * time.Hour},
		{"3m", 3 * time.Minute},
	})
	checkErrors(t, []string{"", "h", "5", "1x", "1h-", " 1h", "1 h", "1h30"})
}

func TestHiddenFraction(t *testing.T) {
	checkParse(t, []parseCase{
		{"1.05h", time.Hour + 3*time.Minute},
		{"0.001s", time.Millisecond},
		{"0.05s", 50 * time.Millisecond},
		{"1.000001s", time.Second + time.Microsecond},
		{"2.0625m", 2*time.Minute + 3750*time.Millisecond},
		{"0.0000001s", 100 * time.Nanosecond},
		{"1.5ms", 1500 * time.Microsecond},
		{"1.50s", 1500 * time.Millisecond},
	})
}

func TestHiddenOrder(t *testing.T) {
	checkParse(t, []parseCase{
		{"1w2d", 9 * day},
		{"1s500ms", 1500 * time.Millisecond},
		{"1m1s1ms1us1ns", time.Minute + time.Second + time.Millisecond + time.Microsecond + time.Nanosecond},
		{"1w1d1h1m1s", week + day + time.Hour + time.Minute + time.Second},
		{"2s3us", 2*time.Second + 3*time.Microsecond},
		{"1h5ns", time.Hour + 5*time.Nanosecond},
	})
}

func TestHiddenOrderErrors(t *testing.T) {
	checkErrors(t, []string{"30m1h", "1h2h", "1d1w", "1ns1s", "500ms1s", "1us1ms", "1s1m", "1h1w"})
}

func TestHiddenFormat(t *testing.T) {
	cases := []struct {
		in   time.Duration
		want string
	}{
		{0, "0s"},
		{90 * time.Minute, "1h30m"},
		{9 * day, "1w2d"},
		{1500 * time.Millisecond, "1s500ms"},
		{-90 * time.Second, "-1m30s"},
	}
	for _, c := range cases {
		if got := duration.Format(c.in); got != c.want {
			t.Errorf("Format(%v) = %q; want %q", c.in, got, c.want)
		}
	}
}

func TestHiddenRoundTrip(t *testing.T) {
	for _, d := range []time.Duration{9 * day, 1500 * time.Millisecond, week + time.Nanosecond, 61 * time.Second} {
		s := duration.Format(d)
		got, err := duration.Parse(s)
		if err != nil || got != d {
			t.Errorf("Parse(Format(%v)) = Parse(%q) = %v, %v", d, s, got, err)
		}
	}
}
