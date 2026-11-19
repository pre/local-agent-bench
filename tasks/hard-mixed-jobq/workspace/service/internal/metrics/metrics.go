// Package metrics keeps counters and writes them in the Prometheus text format.
package metrics

import (
	"fmt"
	"io"
	"net/http"
	"sort"
	"strconv"
	"sync"
)

// Registry is a small set of counters. It is safe for concurrent use.
type Registry struct {
	mu       sync.Mutex
	counters map[string]float64 // key: name and labels, for example name{code="200"}
	help     map[string]string
	gauges   map[string]func() float64
}

// New returns a registry with the counters and gauges of jobq-server.
func New() *Registry {
	return &Registry{
		counters: map[string]float64{},
		help: map[string]string{
			"jobq_jobs_created_total":   "Jobs created.",
			"jobq_jobs_cancelled_total": "Jobs cancelled.",
			"jobq_http_requests_total":  "HTTP requests by status code.",
		},
		gauges: map[string]func() float64{},
	}
}

// Inc adds 1 to the counter name with the labels (pairs of name and value).
func (r *Registry) Inc(name string, labels ...string) {
	key := name
	if len(labels) > 0 {
		key += "{"
		for i := 0; i+1 < len(labels); i += 2 {
			if i > 0 {
				key += ","
			}
			key += labels[i] + "=" + strconv.Quote(labels[i+1])
		}
		key += "}"
	}
	r.mu.Lock()
	r.counters[key]++
	r.mu.Unlock()
}

// Gauge registers a gauge that is read at each scrape.
func (r *Registry) Gauge(name, help string, read func() float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.gauges[name] = read
	r.help[name] = help
}

// Write writes all values in the Prometheus text format.
func (r *Registry) Write(w io.Writer) {
	r.mu.Lock()
	defer r.mu.Unlock()
	for _, name := range []string{"jobq_jobs_created_total", "jobq_jobs_cancelled_total"} {
		if _, ok := r.counters[name]; !ok {
			r.counters[name] = 0
		}
	}
	keys := make([]string, 0, len(r.counters))
	for k := range r.counters {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	written := map[string]bool{}
	for _, key := range keys {
		name := baseName(key)
		if !written[name] {
			fmt.Fprintf(w, "# HELP %s %s\n# TYPE %s counter\n", name, r.help[name], name)
			written[name] = true
		}
		fmt.Fprintf(w, "%s %g\n", key, r.counters[key])
	}
	names := make([]string, 0, len(r.gauges))
	for name := range r.gauges {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		fmt.Fprintf(w, "# HELP %s %s\n# TYPE %s gauge\n%s %g\n", name, r.help[name], name, name, r.gauges[name]())
	}
}

// Handler serves the values.
func (r *Registry) Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		r.Write(w)
	})
}

func baseName(key string) string {
	for i, c := range key {
		if c == '{' {
			return key[:i]
		}
	}
	return key
}
