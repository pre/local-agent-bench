// Package store keeps the jobs of the queue in memory.
package store

import (
	"crypto/rand"
	"encoding/hex"
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

// Job is one entry of the queue. Seq gives the order of creation.
type Job struct {
	ID        string
	Seq       int64
	Command   []string
	Timeout   time.Duration
	State     State
	CreatedAt time.Time
}

// Store is safe for concurrent use.
type Store struct {
	mu     sync.Mutex
	jobs   []*Job // in the order of creation, jobs[i].Seq == i+1
	byID   map[string]*Job
	limit  int
	queued int
	now    func() time.Time
}

// New returns an empty store that accepts at most limit queued jobs.
func New(limit int) *Store {
	return &Store{byID: map[string]*Job{}, limit: limit, now: time.Now}
}

func newID() string {
	var b [8]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	return "j-" + hex.EncodeToString(b[:])
}

// Create adds a queued job.
func (s *Store) Create(command []string, timeout time.Duration) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.queued >= s.limit {
		return Job{}, ErrQueueFull
	}
	id := newID()
	for s.byID[id] != nil {
		id = newID()
	}
	job := &Job{
		ID:        id,
		Seq:       int64(len(s.jobs)) + 1,
		Command:   append([]string(nil), command...),
		Timeout:   timeout,
		State:     Queued,
		CreatedAt: s.now().UTC(),
	}
	s.jobs = append(s.jobs, job)
	s.byID[id] = job
	s.queued++
	return copyJob(job), nil
}

// Get returns the job with the ID.
func (s *Store) Get(id string) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.byID[id]
	if !ok {
		return Job{}, ErrNotFound
	}
	return copyJob(job), nil
}

// Page returns at most size jobs with a Seq after afterSeq, the oldest first,
// and tells if more jobs follow.
func (s *Store) Page(afterSeq int64, size int) ([]Job, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	start := int(afterSeq)
	if start > len(s.jobs) {
		start = len(s.jobs)
	}
	end := min(start+size, len(s.jobs))
	out := make([]Job, 0, end-start)
	for _, job := range s.jobs[start:end] {
		out = append(out, copyJob(job))
	}
	return out, end < len(s.jobs)
}

// LastSeq returns the Seq of the newest job, 0 when there is none.
func (s *Store) LastSeq() int64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	return int64(len(s.jobs))
}

// Cancel changes a queued job to cancelled.
func (s *Store) Cancel(id string) (Job, error) {
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
