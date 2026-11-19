// Package dispatch runs jobs on a fixed number of workers and retries jobs
// that fail.
package dispatch

import (
	"context"
	"errors"
	"sync"
	"time"
)

// ErrClosed is returned by Submit after Close.
var ErrClosed = errors.New("dispatch: dispatcher is closed")

// Job is one unit of work. Node is the name of the node that the job is
// for. It is used only for the statistics.
type Job struct {
	ID   string
	Node string
	Run  func(ctx context.Context) error
}

// Options configure a Dispatcher.
type Options struct {
	// Workers is the number of jobs that run at the same time. Default 4.
	Workers int
	// QueueSize is the capacity of the job queue. Default 64.
	QueueSize int
	// MaxRetries is the number of attempts after the first attempt of a job.
	MaxRetries int
	// Backoff returns the wait time before retry number attempt (starting
	// at 1). If Backoff is nil, a job is retried at once.
	Backoff func(attempt int) time.Duration
}

type task struct {
	job     Job
	attempt int
}

// Dispatcher runs jobs. All methods are safe for concurrent use.
type Dispatcher struct {
	opts   Options
	ctx    context.Context
	cancel context.CancelFunc
	queue  chan task

	workers sync.WaitGroup
	// pending counts the jobs that are accepted but not finished,
	// including jobs that wait for a retry.
	pending sync.WaitGroup

	mu     sync.Mutex
	closed bool
	stats  Stats
}

// New starts a Dispatcher with its workers.
func New(opts Options) *Dispatcher {
	if opts.Workers <= 0 {
		opts.Workers = 4
	}
	if opts.QueueSize <= 0 {
		opts.QueueSize = 64
	}
	ctx, cancel := context.WithCancel(context.Background())
	d := &Dispatcher{
		opts:   opts,
		ctx:    ctx,
		cancel: cancel,
		queue:  make(chan task, opts.QueueSize),
		stats:  Stats{PerNode: make(map[string]*NodeStats)},
	}
	d.workers.Add(opts.Workers)
	for range opts.Workers {
		go d.worker()
	}
	return d
}

// Submit adds a job to the queue. It blocks while the queue is full.
func (d *Dispatcher) Submit(job Job) error {
	d.mu.Lock()
	if d.closed {
		d.mu.Unlock()
		return ErrClosed
	}
	d.stats.recordSubmit(job.Node)
	d.pending.Add(1)
	d.mu.Unlock()

	d.queue <- task{job: job}
	return nil
}

// Close stops accepting jobs and waits until all accepted jobs are
// finished, including their retries.
func (d *Dispatcher) Close() {
	d.mu.Lock()
	if d.closed {
		d.mu.Unlock()
		return
	}
	d.closed = true
	d.mu.Unlock()

	d.pending.Wait()
	close(d.queue)
	d.workers.Wait()
	d.cancel()
}

// Stats returns the current counters.
func (d *Dispatcher) Stats() Stats {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.stats.clone()
}

func (d *Dispatcher) worker() {
	defer d.workers.Done()
	for t := range d.queue {
		d.handle(t)
	}
}

func (d *Dispatcher) handle(t task) {
	start := time.Now()
	err := t.job.Run(d.ctx)
	elapsed := time.Since(start)

	d.mu.Lock()
	d.stats.recordAttempt(t.job.Node, elapsed)
	d.mu.Unlock()

	if err != nil && t.attempt < d.opts.MaxRetries {
		d.retry(t)
		return
	}

	d.mu.Lock()
	d.stats.recordResult(t.job.Node, err == nil)
	d.mu.Unlock()
	d.pending.Done()
}

// retry puts the task back into the queue after the backoff time. The task
// stays pending.
func (d *Dispatcher) retry(t task) {
	t.attempt++
	d.mu.Lock()
	d.stats.recordRetry(t.job.Node)
	d.mu.Unlock()

	var delay time.Duration
	if d.opts.Backoff != nil {
		delay = d.opts.Backoff(t.attempt)
	}
	time.AfterFunc(delay, func() { d.queue <- t })
}
