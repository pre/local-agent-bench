package window

import (
	"testing"
	"time"
)

// 2026-11-16 is a Monday.
var dayOfMonth = map[string]int{"Mon": 16, "Tue": 17, "Wed": 18, "Thu": 19, "Fri": 20, "Sat": 21, "Sun": 22}

func at(day string, hour, minute int) time.Time {
	return time.Date(2026, time.November, dayOfMonth[day], hour, minute, 0, 0, time.UTC)
}

func mustParse(t *testing.T, spec string) Window {
	t.Helper()
	w, err := Parse(spec)
	if err != nil {
		t.Fatalf("Parse(%q): %v", spec, err)
	}
	return w
}

func TestParseErrors(t *testing.T) {
	for _, spec := range []string{
		"",
		"Mon",
		"Mon 09:00",
		"Mon 09:00-",
		"Mon 9:00-10:00",
		"Mon 09:00-10:0",
		"Mon 24:00-10:00",
		"Mon 25:00-26:00",
		"Mon 10:60-11:00",
		"Mon 10:00-11:60",
		"Mon 10:00-24:01",
		"Mon 10:00-10:00",
		"Monday 10:00-11:00",
		"mon 10:00-11:00",
		"Mon,Xyz 10:00-11:00",
		"Mon-Xyz 10:00-11:00",
		"Mon 1a:00-11:00",
	} {
		if _, err := Parse(spec); err == nil {
			t.Errorf("Parse(%q): no error", spec)
		}
	}
}

func TestContains(t *testing.T) {
	tests := []struct {
		spec string
		t    time.Time
		want bool
	}{
		{"Mon 09:00-17:00", at("Mon", 9, 0), true},
		{"Mon 09:00-17:00", at("Mon", 8, 59), false},
		{"Mon 09:00-17:00", at("Mon", 16, 59), true},
		{"Mon 09:00-17:00", at("Mon", 17, 0), false},
		{"Mon 09:00-17:00", at("Tue", 10, 0), false},
		{"Mon 09:00-17:00", at("Sun", 10, 0), false},
		{"Sat 20:00-24:00", at("Sat", 23, 59), true},
		{"Sat 20:00-24:00", at("Sun", 0, 0), false},
		// Crosses midnight.
		{"Fri 22:00-02:00", at("Fri", 22, 0), true},
		{"Fri 22:00-02:00", at("Fri", 21, 59), false},
		{"Fri 22:00-02:00", at("Sat", 0, 0), true},
		{"Fri 22:00-02:00", at("Sat", 1, 59), true},
		{"Fri 22:00-02:00", at("Sat", 2, 0), false},
		{"Fri 22:00-02:00", at("Fri", 1, 0), false},
		{"Fri 22:00-02:00", at("Sat", 22, 30), false},
		{"Sun 23:00-01:00", at("Mon", 0, 30), true},
		{"Sun 23:00-01:00", at("Sun", 0, 30), false},
		// Day lists and ranges.
		{"Mon-Fri 08:00-09:00", at("Wed", 8, 30), true},
		{"Mon-Fri 08:00-09:00", at("Fri", 8, 30), true},
		{"Mon-Fri 08:00-09:00", at("Sat", 8, 30), false},
		{"Fri-Mon 08:00-09:00", at("Sun", 8, 30), true},
		{"Fri-Mon 08:00-09:00", at("Mon", 8, 30), true},
		{"Fri-Mon 08:00-09:00", at("Tue", 8, 30), false},
		{"Sun-Sat 08:00-09:00", at("Wed", 8, 30), true},
		{"Mon,Wed,Fri 08:00-09:00", at("Wed", 8, 30), true},
		{"Mon,Wed,Fri 08:00-09:00", at("Fri", 8, 30), true},
		{"Mon,Wed,Fri 08:00-09:00", at("Thu", 8, 30), false},
		{"Tue,Sat-Sun 08:00-09:00", at("Sun", 8, 30), true},
		{"* 03:00-04:00", at("Thu", 3, 15), true},
		{"* 03:00-04:00", at("Thu", 4, 15), false},
		{"Mon 10:59-11:00", at("Mon", 10, 59).Add(59 * time.Second), true},
	}
	for _, tt := range tests {
		w := mustParse(t, tt.spec)
		if got := w.Contains(tt.t); got != tt.want {
			t.Errorf("%q.Contains(%s) = %v, want %v", tt.spec, tt.t.Format("Mon 15:04:05"), got, tt.want)
		}
	}
}

func TestContainsUsesLocationOfTime(t *testing.T) {
	w := mustParse(t, "Mon 09:00-17:00")
	helsinki := time.FixedZone("EET", 2*60*60)
	local := time.Date(2026, time.November, 16, 9, 30, 0, 0, helsinki) // 07:30 UTC
	if !w.Contains(local) {
		t.Errorf("Contains(%s) = false, want true", local)
	}
	late := time.Date(2026, time.November, 16, 18, 0, 0, 0, helsinki) // 16:00 UTC
	if w.Contains(late) {
		t.Errorf("Contains(%s) = true, want false", late)
	}
}

func TestNext(t *testing.T) {
	tests := []struct {
		spec string
		t    time.Time
		want time.Time
	}{
		{"Mon 09:00-17:00", at("Mon", 10, 0), at("Mon", 10, 0)},
		{"Mon 09:00-17:00", at("Mon", 9, 0), at("Mon", 9, 0)},
		{"Mon 09:00-17:00", at("Mon", 8, 0), at("Mon", 9, 0)},
		{"Mon 09:00-17:00", at("Mon", 17, 0), at("Mon", 9, 0).AddDate(0, 0, 7)},
		{"Mon 09:00-17:00", at("Sun", 23, 0), at("Mon", 9, 0).AddDate(0, 0, 7)},
		{"Mon 09:00-17:00", at("Tue", 0, 0), at("Mon", 9, 0).AddDate(0, 0, 7)},
		{"Mon-Fri 22:00-02:00", at("Sat", 1, 0), at("Sat", 1, 0)},
		{"Mon-Fri 22:00-02:00", at("Sat", 3, 0), at("Mon", 22, 0).AddDate(0, 0, 7)},
		{"Wed,Fri 06:00-07:00", at("Wed", 7, 0), at("Fri", 6, 0)},
		{"* 06:00-07:00", at("Wed", 7, 0), at("Thu", 6, 0)},
	}
	for _, tt := range tests {
		w := mustParse(t, tt.spec)
		if got := w.Next(tt.t); !got.Equal(tt.want) {
			t.Errorf("%q.Next(%s) = %s, want %s", tt.spec, tt.t, got, tt.want)
		}
	}
}

func TestNextKeepsLocation(t *testing.T) {
	w := mustParse(t, "Mon 09:00-17:00")
	helsinki := time.FixedZone("EET", 2*60*60)
	from := time.Date(2026, time.November, 16, 8, 0, 0, 0, helsinki)
	got := w.Next(from)
	want := time.Date(2026, time.November, 16, 9, 0, 0, 0, helsinki)
	if !got.Equal(want) || got.Location() != helsinki {
		t.Errorf("Next(%s) = %s, want %s", from, got, want)
	}
}

func TestDuration(t *testing.T) {
	tests := []struct {
		spec string
		want time.Duration
	}{
		{"Mon 09:00-17:30", 8*time.Hour + 30*time.Minute},
		{"Fri 22:00-02:00", 4 * time.Hour},
		{"Sat 20:00-24:00", 4 * time.Hour},
		{"Sun 00:01-00:00", 23*time.Hour + 59*time.Minute},
	}
	for _, tt := range tests {
		if got := mustParse(t, tt.spec).Duration(); got != tt.want {
			t.Errorf("%q.Duration() = %s, want %s", tt.spec, got, tt.want)
		}
	}
}
