// Package window parses weekly maintenance windows and tells if a time is
// inside one.
//
// A window spec has the form "<days> <start>-<end>", for example
// "Mon-Fri 22:00-02:00".
//
// <days> is "*" for all days, or a comma-separated list of items. An item
// is one day ("Mon") or a range of days ("Mon-Fri"). A range can go past
// Sunday: "Fri-Mon" is Friday, Saturday, Sunday and Monday. The day names
// are Mon, Tue, Wed, Thu, Fri, Sat and Sun.
//
// <start> and <end> are times of day in the form HH:MM (24-hour clock,
// two digits each). <end> can also be "24:00", the end of the day. The
// start time is inside the window, the end time is not. If <end> is before
// <start>, the window crosses midnight: it opens on each listed day at
// <start> and closes on the next day at <end>. A window with the same start
// and end is an error.
//
// A time is evaluated in its own location (time zone).
package window

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

const minutesPerDay = 24 * 60

// dayNames is indexed by time.Weekday.
var dayNames = [7]string{"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"}

// Window is a weekly maintenance window.
type Window struct {
	days  [7]bool // the days on which the window opens, by time.Weekday
	start int     // minutes after midnight
	end   int     // minutes after midnight, minutesPerDay for "24:00"
}

// Parse parses a window spec.
func Parse(spec string) (Window, error) {
	daysText, timesText, ok := strings.Cut(strings.TrimSpace(spec), " ")
	if !ok {
		return Window{}, fmt.Errorf("window %q: want \"<days> <start>-<end>\"", spec)
	}
	var w Window
	if err := w.parseDays(daysText); err != nil {
		return Window{}, fmt.Errorf("window %q: %w", spec, err)
	}
	startText, endText, ok := strings.Cut(strings.TrimSpace(timesText), "-")
	if !ok {
		return Window{}, fmt.Errorf("window %q: want <start>-<end>", spec)
	}
	var err error
	if w.start, err = parseClock(startText, false); err != nil {
		return Window{}, fmt.Errorf("window %q: start: %w", spec, err)
	}
	if w.end, err = parseClock(endText, true); err != nil {
		return Window{}, fmt.Errorf("window %q: end: %w", spec, err)
	}
	if w.start == w.end {
		return Window{}, fmt.Errorf("window %q: start and end are the same", spec)
	}
	return w, nil
}

func (w *Window) parseDays(text string) error {
	if text == "*" {
		for d := range w.days {
			w.days[d] = true
		}
		return nil
	}
	for _, item := range strings.Split(text, ",") {
		fromText, toText, isRange := strings.Cut(item, "-")
		from, err := parseDay(fromText)
		if err != nil {
			return err
		}
		to := from
		if isRange {
			if to, err = parseDay(toText); err != nil {
				return err
			}
		}
		for d := from; ; d = (d + 1) % 7 {
			w.days[d] = true
			if d == to {
				break
			}
		}
	}
	return nil
}

func parseDay(text string) (int, error) {
	for d, name := range dayNames {
		if text == name {
			return d, nil
		}
	}
	return 0, fmt.Errorf("unknown day %q", text)
}

// parseClock returns the minutes after midnight of an HH:MM time. "24:00"
// is valid only for an end time.
func parseClock(text string, isEnd bool) (int, error) {
	hh, mm, ok := strings.Cut(text, ":")
	if !ok || !isTwoDigits(hh) || !isTwoDigits(mm) {
		return 0, fmt.Errorf("invalid time %q, want HH:MM", text)
	}
	h, _ := strconv.Atoi(hh)
	m, _ := strconv.Atoi(mm)
	if isEnd && h == 24 && m == 0 {
		return minutesPerDay, nil
	}
	if h > 23 || m > 59 {
		return 0, fmt.Errorf("invalid time %q", text)
	}
	return h*60 + m, nil
}

func isTwoDigits(s string) bool {
	return len(s) == 2 && s[0] >= '0' && s[0] <= '9' && s[1] >= '0' && s[1] <= '9'
}

// crossesMidnight reports whether the window closes on the day after it
// opens.
func (w Window) crossesMidnight() bool {
	return w.end < w.start
}

// Duration returns the length of one opening of the window.
func (w Window) Duration() time.Duration {
	minutes := w.end - w.start
	if w.crossesMidnight() {
		minutes += minutesPerDay
	}
	return time.Duration(minutes) * time.Minute
}

// Contains reports whether t is inside the window. Seconds and smaller
// units of t are not used: 21:59:59 is in the minute 21:59.
func (w Window) Contains(t time.Time) bool {
	minute := t.Hour()*60 + t.Minute()
	today := int(t.Weekday())
	if !w.crossesMidnight() {
		return w.days[today] && minute >= w.start && minute < w.end
	}
	yesterday := (today + 6) % 7
	return (w.days[today] && minute >= w.start) || (w.days[yesterday] && minute < w.end)
}

// Next returns t if t is inside the window. Otherwise it returns the time
// at which the window opens next. The result is in the location of t.
func (w Window) Next(t time.Time) time.Time {
	if w.Contains(t) {
		return t
	}
	for i := 0; i < 7; i++ {
		day := time.Date(t.Year(), t.Month(), t.Day()+i, 0, 0, 0, 0, t.Location())
		if !w.days[day.Weekday()] {
			continue
		}
		open := time.Date(day.Year(), day.Month(), day.Day(), w.start/60, w.start%60, 0, 0, t.Location())
		if !open.Before(t) {
			return open
		}
	}
	panic("window: Next found no opening")
}
