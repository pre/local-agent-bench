// Package store keeps the jobs of the queue in memory.
package store

import (
	"errors"
	"sync"
	"time"
)

// State is the state of a job.
type State string

const (
	Queued    State = "queued"
	Cancelled State = "cancelled"
)

var (
	ErrNotFound  = errors.New("job not found")
	ErrQueueFull = errors.New("queue is full")
	ErrNotQueued = errors.New("job is not queued")
)

// Job is one entry of the queue.
type Job struct {
	ID             int64
	Command        []string
	TimeoutSeconds int
	State          State
	CreatedAt      time.Time
}

// Store is safe for concurrent use.
type Store struct {
	mu     sync.Mutex
	jobs   []*Job // in the order of creation
	byID   map[int64]*Job
	nextID int64
	limit  int
	queued int
	now    func() time.Time
}

// New returns an empty store that accepts at most limit queued jobs.
func New(limit int) *Store {
	return &Store{byID: map[int64]*Job{}, nextID: 1, limit: limit, now: time.Now}
}

// Create adds a queued job.
func (s *Store) Create(command []string, timeoutSeconds int) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.queued >= s.limit {
		return Job{}, ErrQueueFull
	}
	job := &Job{
		ID:             s.nextID,
		Command:        append([]string(nil), command...),
		TimeoutSeconds: timeoutSeconds,
		State:          Queued,
		CreatedAt:      s.now().UTC(),
	}
	s.nextID++
	s.jobs = append(s.jobs, job)
	s.byID[job.ID] = job
	s.queued++
	return copyJob(job), nil
}

// Get returns the job with the ID.
func (s *Store) Get(id int64) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.byID[id]
	if !ok {
		return Job{}, ErrNotFound
	}
	return copyJob(job), nil
}

// List returns all jobs, the oldest first.
func (s *Store) List() []Job {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]Job, 0, len(s.jobs))
	for _, job := range s.jobs {
		out = append(out, copyJob(job))
	}
	return out
}

// Cancel changes a queued job to cancelled.
func (s *Store) Cancel(id int64) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.byID[id]
	if !ok {
		return Job{}, ErrNotFound
	}
	if job.State != Queued {
		return Job{}, ErrNotQueued
	}
	job.State = Cancelled
	s.queued--
	return copyJob(job), nil
}

// QueuedCount returns the number of queued jobs.
func (s *Store) QueuedCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.queued
}

func copyJob(job *Job) Job {
	out := *job
	out.Command = append([]string(nil), job.Command...)
	return out
}
