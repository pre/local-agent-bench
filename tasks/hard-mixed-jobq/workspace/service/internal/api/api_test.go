package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"example.internal/jobq/internal/config"
	"example.internal/jobq/internal/metrics"
	"example.internal/jobq/internal/store"
)

func newTestServer(t *testing.T, limit int) *httptest.Server {
	t.Helper()
	cfg := config.Defaults()
	cfg.QueueLimit = limit
	srv := httptest.NewServer(New(cfg, store.New(limit), metrics.New()).Handler())
	t.Cleanup(srv.Close)
	return srv
}

func do(t *testing.T, method, url, body string) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(method, url, strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var sb strings.Builder
	buf := make([]byte, 4096)
	for {
		n, err := resp.Body.Read(buf)
		sb.Write(buf[:n])
		if err != nil {
			break
		}
	}
	return resp, sb.String()
}

func TestCreateAndGet(t *testing.T) {
	srv := newTestServer(t, 10)
	resp, body := do(t, "POST", srv.URL+"/v1/jobs", `{"command": ["echo", "hi"], "timeout_seconds": 90}`)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("status %d: %s", resp.StatusCode, body)
	}
	var job jobJSON
	if err := json.Unmarshal([]byte(body), &job); err != nil {
		t.Fatal(err)
	}
	if job.ID != 1 || job.TimeoutSeconds != 90 || job.State != "queued" {
		t.Fatalf("job %+v", job)
	}
	resp, body = do(t, "GET", srv.URL+"/v1/jobs/1", "")
	if resp.StatusCode != http.StatusOK || !strings.Contains(body, `"echo"`) {
		t.Fatalf("status %d: %s", resp.StatusCode, body)
	}
}

func TestCreateValidation(t *testing.T) {
	srv := newTestServer(t, 10)
	for _, body := range []string{
		`{"command": [], "timeout_seconds": 5}`,
		`{"command": ["true"]}`,
		`{"command": ["true"], "timeout_seconds": 0}`,
		`{"command": ["true"], "timeout_seconds": 3601}`,
		`{"command": ["true"], "timeout_seconds": 5, "extra": 1}`,
		`not json`,
	} {
		resp, _ := do(t, "POST", srv.URL+"/v1/jobs", body)
		if resp.StatusCode != http.StatusBadRequest {
			t.Errorf("%s: status %d, want 400", body, resp.StatusCode)
		}
	}
}

func TestListAndCancel(t *testing.T) {
	srv := newTestServer(t, 10)
	for i := 0; i < 3; i++ {
		do(t, "POST", srv.URL+"/v1/jobs", `{"command": ["true"], "timeout_seconds": 5}`)
	}
	resp, body := do(t, "DELETE", srv.URL+"/v1/jobs/2", "")
	if resp.StatusCode != http.StatusOK || !strings.Contains(body, `"cancelled"`) {
		t.Fatalf("cancel: %d %s", resp.StatusCode, body)
	}
	resp, _ = do(t, "DELETE", srv.URL+"/v1/jobs/2", "")
	if resp.StatusCode != http.StatusConflict {
		t.Fatalf("second cancel: %d", resp.StatusCode)
	}
	_, body = do(t, "GET", srv.URL+"/v1/jobs", "")
	var jobs []jobJSON
	if err := json.Unmarshal([]byte(body), &jobs); err != nil {
		t.Fatal(err)
	}
	if len(jobs) != 3 || jobs[1].State != "cancelled" {
		t.Fatalf("list %+v", jobs)
	}
}

func TestErrors(t *testing.T) {
	srv := newTestServer(t, 1)
	do(t, "POST", srv.URL+"/v1/jobs", `{"command": ["true"], "timeout_seconds": 5}`)
	resp, _ := do(t, "POST", srv.URL+"/v1/jobs", `{"command": ["true"], "timeout_seconds": 5}`)
	if resp.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("queue full: %d", resp.StatusCode)
	}
	resp, _ = do(t, "GET", srv.URL+"/v1/jobs/42", "")
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("unknown job: %d", resp.StatusCode)
	}
	resp, _ = do(t, "GET", srv.URL+"/v1/jobs/abc", "")
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("bad ID: %d", resp.StatusCode)
	}
}

func TestHealthAndMetrics(t *testing.T) {
	srv := newTestServer(t, 10)
	resp, _ := do(t, "GET", srv.URL+"/healthz", "")
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("healthz: %d", resp.StatusCode)
	}
	do(t, "POST", srv.URL+"/v1/jobs", `{"command": ["true"], "timeout_seconds": 5}`)
	_, body := do(t, "GET", srv.URL+"/metrics", "")
	if !strings.Contains(body, "jobq_jobs_created_total 1") {
		t.Fatalf("metrics:\n%s", body)
	}
}
