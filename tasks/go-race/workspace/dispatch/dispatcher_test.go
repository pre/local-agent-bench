package dispatch

import (
	"context"
	"errors"
	"fmt"
	"sync/atomic"
	"testing"
	"time"
)

var errFlaky = errors.New("flaky")

// flakyJob fails in its first failFirst attempts.
func flakyJob(id int, node string, failFirst int, attempts *atomic.Int64) Job {
	var tries atomic.Int64
	return Job{
		ID:   fmt.Sprintf("job-%d", id),
		Node: node,
		Run: func(ctx context.Context) error {
			if attempts != nil {
				attempts.Add(1)
			}
			if tries.Add(1) <= int64(failFirst) {
				return errFlaky
			}
			return nil
		},
	}
}

func TestSequentialCounts(t *testing.T) {
	d := New(Options{Workers: 1, MaxRetries: 1})
	for i := range 6 {
		if err := d.Submit(flakyJob(i, "n1", i%3, nil)); err != nil {
			t.Fatal(err)
		}
	}
	d.Close()
	s := d.Stats()
	// failFirst 0,1,2,0,1,2: 4 succeed, 2 fail after one retry each.
	if s.Submitted != 6 || s.Succeeded != 4 || s.Failed != 2 || s.Retried != 4 {
		t.Errorf("got %+v", s)
	}
	if s.InFlight() != 0 {
		t.Errorf("InFlight() = %d after Close", s.InFlight())
	}
	ns := s.PerNode["n1"]
	if ns == nil || ns.Submitted != 6 || ns.Succeeded != 4 || ns.Failed != 2 || ns.Retried != 4 {
		t.Errorf("node n1: got %+v", ns)
	}
}

func TestSubmitAfterClose(t *testing.T) {
	d := New(Options{Workers: 2})
	d.Close()
	if err := d.Submit(flakyJob(1, "n1", 0, nil)); !errors.Is(err, ErrClosed) {
		t.Errorf("Submit after Close: got %v, want ErrClosed", err)
	}
	d.Close()
}

func TestRetryLimit(t *testing.T) {
	var attempts atomic.Int64
	d := New(Options{Workers: 3, MaxRetries: 3, Backoff: func(int) time.Duration { return time.Millisecond }})
	if err := d.Submit(flakyJob(1, "n1", 100, &attempts)); err != nil {
		t.Fatal(err)
	}
	d.Close()
	s := d.Stats()
	if got := attempts.Load(); got != 4 {
		t.Errorf("attempts = %d, want 4", got)
	}
	if s.Failed != 1 || s.Succeeded != 0 || s.Retried != 3 {
		t.Errorf("got %+v", s)
	}
}
