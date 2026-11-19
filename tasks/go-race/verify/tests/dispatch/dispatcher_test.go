package dispatch

import (
	"context"
	"errors"
	"fmt"
	"sync"
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

type expected struct {
	succeeded, failed, retried int
	perNode                    map[string]NodeStats
}

// runLoad submits jobs from several producers. Job i fails in its first
// i%4 attempts and is for node i%nodes.
func runLoad(t *testing.T, d *Dispatcher, from, to, producers, nodes, maxRetries int) expected {
	t.Helper()
	exp := expected{perNode: make(map[string]NodeStats)}
	for i := from; i < to; i++ {
		node := fmt.Sprintf("node-%02d", i%nodes)
		ns := exp.perNode[node]
		failFirst := i % 4
		ns.Submitted++
		retries := min(failFirst, maxRetries)
		ns.Retried += retries
		exp.retried += retries
		if failFirst <= maxRetries {
			ns.Succeeded++
			exp.succeeded++
		} else {
			ns.Failed++
			exp.failed++
		}
		exp.perNode[node] = ns
	}

	var wg sync.WaitGroup
	for p := range producers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := from + p; i < to; i += producers {
				if err := d.Submit(flakyJob(i, fmt.Sprintf("node-%02d", i%nodes), i%4, nil)); err != nil {
					t.Error(err)
					return
				}
			}
		}()
	}
	wg.Wait()
	return exp
}

func checkStats(t *testing.T, s Stats, submitted int, exp expected) {
	t.Helper()
	if s.Submitted != submitted || s.Succeeded != exp.succeeded || s.Failed != exp.failed || s.Retried != exp.retried {
		t.Errorf("totals: got submitted=%d succeeded=%d failed=%d retried=%d, want %d %d %d %d",
			s.Submitted, s.Succeeded, s.Failed, s.Retried, submitted, exp.succeeded, exp.failed, exp.retried)
	}
	if len(s.PerNode) != len(exp.perNode) {
		t.Errorf("got %d nodes, want %d", len(s.PerNode), len(exp.perNode))
	}
	for node, want := range exp.perNode {
		got := s.PerNode[node]
		if got == nil {
			t.Errorf("node %s missing", node)
			continue
		}
		g := *got
		g.Busy = 0
		if g != want {
			t.Errorf("node %s: got %+v, want %+v", node, g, want)
		}
	}
}

func TestCountsUnderLoad(t *testing.T) {
	for round := range 3 {
		d := New(Options{Workers: 16, QueueSize: 32, MaxRetries: 2})
		exp := runLoad(t, d, 0, 4000, 8, 12, 2)
		d.Close()
		checkStats(t, d.Stats(), 4000, exp)
		if t.Failed() {
			t.Fatalf("round %d failed", round)
		}
	}
}

func TestStatsWhileRunning(t *testing.T) {
	d := New(Options{Workers: 16, MaxRetries: 2})

	stop := make(chan struct{})
	done := make(chan int)
	go func() {
		polls := 0
		for {
			s := d.Stats()
			var succeeded, failed, retried int
			for _, ns := range s.PerNode {
				succeeded += ns.Succeeded
				failed += ns.Failed
				retried += ns.Retried
			}
			if succeeded != s.Succeeded || failed != s.Failed || retried != s.Retried {
				t.Errorf("snapshot does not add up: totals %d/%d/%d, nodes %d/%d/%d",
					s.Succeeded, s.Failed, s.Retried, succeeded, failed, retried)
			}
			if s.InFlight() < 0 {
				t.Errorf("InFlight() = %d", s.InFlight())
			}
			polls++
			select {
			case <-stop:
				done <- polls
				return
			default:
			}
		}
	}()

	exp := runLoad(t, d, 0, 4000, 8, 12, 2)
	d.Close()
	close(stop)
	if polls := <-done; polls < 2 {
		t.Fatalf("only %d polls", polls)
	}
	checkStats(t, d.Stats(), 4000, exp)
}

func TestStatsSnapshotIsolated(t *testing.T) {
	d := New(Options{Workers: 4, MaxRetries: 2})
	first := runLoad(t, d, 0, 400, 2, 5, 2)

	// Wait until the first jobs are finished, then take a snapshot.
	deadline := time.Now().Add(20 * time.Second)
	for d.Stats().InFlight() > 0 {
		if time.Now().After(deadline) {
			t.Fatal("jobs did not finish")
		}
		time.Sleep(time.Millisecond)
	}
	snapshot := d.Stats()

	runLoad(t, d, 400, 800, 2, 5, 2)
	d.Close()

	checkStats(t, snapshot, 400, first)
	if after := d.Stats(); after.Submitted != 800 {
		t.Errorf("after: submitted %d, want 800", after.Submitted)
	}
}
