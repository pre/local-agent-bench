// Package api has the HTTP handlers of jobq-server (contract v1).
package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"time"

	"example.internal/jobq/internal/config"
	"example.internal/jobq/internal/metrics"
	"example.internal/jobq/internal/store"
)

const maxBodyBytes = 64 << 10

// Server serves the API, the health check and the metrics.
type Server struct {
	cfg     config.Config
	store   *store.Store
	metrics *metrics.Registry
}

// New returns a server.
func New(cfg config.Config, st *store.Store, m *metrics.Registry) *Server {
	return &Server{cfg: cfg, store: st, metrics: m}
}

// jobJSON is the JSON form of a job.
type jobJSON struct {
	ID             int64     `json:"id"`
	Command        []string  `json:"command"`
	TimeoutSeconds int       `json:"timeout_seconds"`
	State          string    `json:"state"`
	CreatedAt      time.Time `json:"created_at"`
}

type createRequest struct {
	Command        []string `json:"command"`
	TimeoutSeconds *int     `json:"timeout_seconds"`
}

// Handler returns the HTTP handler with all routes.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		io.WriteString(w, "ok\n")
	})
	mux.Handle("GET /metrics", s.metrics.Handler())
	mux.HandleFunc("POST /v1/jobs", s.createJob)
	mux.HandleFunc("GET /v1/jobs", s.listJobs)
	mux.HandleFunc("GET /v1/jobs/{id}", s.getJob)
	mux.HandleFunc("DELETE /v1/jobs/{id}", s.cancelJob)
	return s.countRequests(mux)
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
		writeError(w, http.StatusBadRequest, "invalid JSON body: "+err.Error())
		return
	}
	if len(req.Command) == 0 {
		writeError(w, http.StatusBadRequest, "command must not be empty")
		return
	}
	if req.TimeoutSeconds == nil {
		writeError(w, http.StatusBadRequest, "timeout_seconds is required")
		return
	}
	if *req.TimeoutSeconds < 1 || *req.TimeoutSeconds > s.cfg.MaxTimeoutSeconds {
		writeError(w, http.StatusBadRequest,
			fmt.Sprintf("timeout_seconds must be from 1 to %d", s.cfg.MaxTimeoutSeconds))
		return
	}
	job, err := s.store.Create(req.Command, *req.TimeoutSeconds)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	s.metrics.Inc("jobq_jobs_created_total")
	writeJSON(w, http.StatusCreated, toJSON(job))
}

func (s *Server) listJobs(w http.ResponseWriter, _ *http.Request) {
	jobs := s.store.List()
	out := make([]jobJSON, 0, len(jobs))
	for _, job := range jobs {
		out = append(out, toJSON(job))
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) getJob(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(w, r)
	if !ok {
		return
	}
	job, err := s.store.Get(id)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, toJSON(job))
}

func (s *Server) cancelJob(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(w, r)
	if !ok {
		return
	}
	job, err := s.store.Cancel(id)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	s.metrics.Inc("jobq_jobs_cancelled_total")
	writeJSON(w, http.StatusOK, toJSON(job))
}

func parseID(w http.ResponseWriter, r *http.Request) (int64, bool) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id < 1 {
		writeError(w, http.StatusBadRequest, "job ID must be a positive integer")
		return 0, false
	}
	return id, true
}

func toJSON(job store.Job) jobJSON {
	return jobJSON{
		ID:             job.ID,
		Command:        job.Command,
		TimeoutSeconds: job.TimeoutSeconds,
		State:          string(job.State),
		CreatedAt:      job.CreatedAt,
	}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
