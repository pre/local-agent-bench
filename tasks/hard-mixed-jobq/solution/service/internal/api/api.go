// Package api has the HTTP handlers of jobq-server (contract version 2).
package api

import (
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"example.internal/jobq/internal/config"
	"example.internal/jobq/internal/metrics"
	"example.internal/jobq/internal/store"
)

const (
	maxBodyBytes    = 64 << 10
	defaultPageSize = 50
	maxPageSize     = 200
)

// Server serves the API and the probes. The metrics have their own listener.
type Server struct {
	cfg      config.Config
	token    string
	store    *store.Store
	metrics  *metrics.Registry
	draining atomic.Bool
}

// New returns a server that accepts requests with the token.
func New(cfg config.Config, token string, st *store.Store, m *metrics.Registry) *Server {
	return &Server{cfg: cfg, token: token, store: st, metrics: m}
}

// StartDrain makes /readyz answer 503. All other requests continue.
func (s *Server) StartDrain() {
	s.draining.Store(true)
}

type jobJSON struct {
	ID        string    `json:"id"`
	Command   []string  `json:"command"`
	Timeout   string    `json:"timeout"`
	State     string    `json:"state"`
	CreatedAt time.Time `json:"created_at"`
}

type pageJSON struct {
	Jobs          []jobJSON `json:"jobs"`
	NextPageToken string    `json:"next_page_token"`
}

type createRequest struct {
	Command *[]string `json:"command"`
	Timeout *string   `json:"timeout"`
}

// Handler returns the HTTP handler of the API listener.
func (s *Server) Handler() http.Handler {
	v2 := http.NewServeMux()
	v2.HandleFunc("POST /v2/jobs", s.createJob)
	v2.HandleFunc("GET /v2/jobs", s.listJobs)
	v2.HandleFunc("GET /v2/jobs/{id}", s.getJob)
	v2.HandleFunc("POST /v2/jobs/{id}/cancel", s.cancelJob)
	v2.HandleFunc("/v2/", func(w http.ResponseWriter, r *http.Request) {
		writeError(w, codeNotFound, "no such path: "+r.URL.Path)
	})

	mux := http.NewServeMux()
	mux.HandleFunc("GET /livez", func(w http.ResponseWriter, _ *http.Request) {
		io.WriteString(w, "ok\n")
	})
	mux.HandleFunc("GET /readyz", func(w http.ResponseWriter, _ *http.Request) {
		if s.draining.Load() {
			http.Error(w, "draining", http.StatusServiceUnavailable)
			return
		}
		io.WriteString(w, "ok\n")
	})
	mux.Handle("/v2/", s.authenticate(v2))
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		writeError(w, codeNotFound, "no such path: "+r.URL.Path)
	})
	return s.countRequests(mux)
}

func (s *Server) authenticate(next http.Handler) http.Handler {
	want := []byte("Bearer " + s.token)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got := []byte(r.Header.Get("Authorization"))
		if subtle.ConstantTimeCompare(got, want) != 1 {
			writeError(w, codeUnauthenticated, "missing or wrong bearer token")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) countRequests(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		s.metrics.Inc("jobq_http_requests_total", "code", strconv.Itoa(rec.status))
	})
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}

func (s *Server) createJob(w http.ResponseWriter, r *http.Request) {
	var req createRequest
	dec := json.NewDecoder(io.LimitReader(r.Body, maxBodyBytes))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&req); err != nil {
		writeError(w, codeInvalidArgument, "invalid JSON body: "+err.Error())
		return
	}
	if req.Command == nil || len(*req.Command) == 0 {
		writeError(w, codeInvalidArgument, "command must be a list of 1 or more strings")
		return
	}
	if req.Timeout == nil {
		writeError(w, codeInvalidArgument, "timeout is required")
		return
	}
	timeout, err := time.ParseDuration(*req.Timeout)
	if err != nil || timeout <= 0 || timeout > s.cfg.MaxTimeout {
		writeError(w, codeInvalidArgument,
			fmt.Sprintf("timeout must be a duration more than 0 and not more than %v", s.cfg.MaxTimeout))
		return
	}
	job, err := s.store.Create(*req.Command, timeout)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	s.metrics.Inc("jobq_jobs_created_total")
	writeJSON(w, http.StatusCreated, toJSON(job))
}

func (s *Server) listJobs(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	size := defaultPageSize
	if q.Has("page_size") {
		n, err := strconv.Atoi(q.Get("page_size"))
		if err != nil || n < 1 || n > maxPageSize {
			writeError(w, codeInvalidArgument, fmt.Sprintf("page_size must be from 1 to %d", maxPageSize))
			return
		}
		size = n
	}
	var after int64
	if tok := q.Get("page_token"); tok != "" {
		seq, ok := decodeToken(tok)
		if !ok || seq < 1 || seq > s.store.LastSeq() {
			writeError(w, codeInvalidArgument, "page_token is not valid")
			return
		}
		after = seq
	}
	jobs, more := s.store.Page(after, size)
	page := pageJSON{Jobs: make([]jobJSON, 0, len(jobs))}
	for _, job := range jobs {
		page.Jobs = append(page.Jobs, toJSON(job))
	}
	if more {
		page.NextPageToken = encodeToken(jobs[len(jobs)-1].Seq)
	}
	writeJSON(w, http.StatusOK, page)
}

func encodeToken(seq int64) string {
	return base64.RawURLEncoding.EncodeToString([]byte("after:" + strconv.FormatInt(seq, 10)))
}

func decodeToken(tok string) (int64, bool) {
	raw, err := base64.RawURLEncoding.DecodeString(tok)
	if err != nil {
		return 0, false
	}
	rest, ok := strings.CutPrefix(string(raw), "after:")
	if !ok {
		return 0, false
	}
	seq, err := strconv.ParseInt(rest, 10, 64)
	return seq, err == nil
}

func (s *Server) getJob(w http.ResponseWriter, r *http.Request) {
	job, err := s.store.Get(r.PathValue("id"))
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, toJSON(job))
}

func (s *Server) cancelJob(w http.ResponseWriter, r *http.Request) {
	job, err := s.store.Cancel(r.PathValue("id"))
	if err != nil {
		writeStoreError(w, err)
		return
	}
	s.metrics.Inc("jobq_jobs_cancelled_total")
	writeJSON(w, http.StatusOK, toJSON(job))
}

func toJSON(job store.Job) jobJSON {
	return jobJSON{
		ID:        job.ID,
		Command:   job.Command,
		Timeout:   job.Timeout.String(),
		State:     string(job.State),
		CreatedAt: job.CreatedAt,
	}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
