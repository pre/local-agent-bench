package api

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"example.internal/jobq/internal/config"
	"example.internal/jobq/internal/metrics"
	"example.internal/jobq/internal/store"
)

const testToken = "test-token"

func newTestServer(t *testing.T, limit int) (*httptest.Server, *Server) {
	t.Helper()
	cfg := config.Defaults()
	cfg.QueueLimit = limit
	s := New(cfg, testToken, store.New(limit), metrics.New())
	srv := httptest.NewServer(s.Handler())
	t.Cleanup(srv.Close)
	return srv, s
}

func do(t *testing.T, method, url, token, body string) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(method, url, strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	return resp, string(data)
}

func errorCode(t *testing.T, body string) string {
	t.Helper()
	var e errorBody
	if err := json.Unmarshal([]byte(body), &e); err != nil {
		t.Fatalf("error body %q: %v", body, err)
	}
	return e.Error.Code
}

func TestCreateGetCancel(t *testing.T) {
	srv, _ := newTestServer(t, 10)
	resp, body := do(t, "POST", srv.URL+"/v2/jobs", testToken, `{"command": ["echo", "hi"], "timeout": "90s"}`)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("status %d: %s", resp.StatusCode, body)
	}
	var job jobJSON
	json.Unmarshal([]byte(body), &job)
	if job.ID == "" || job.Timeout != "1m30s" || job.State != "queued" {
		t.Fatalf("job %+v", job)
	}
	resp, body = do(t, "GET", srv.URL+"/v2/jobs/"+job.ID, testToken, "")
	if resp.StatusCode != http.StatusOK || !strings.Contains(body, `"echo"`) {
		t.Fatalf("get: %d %s", resp.StatusCode, body)
	}
	resp, body = do(t, "POST", srv.URL+"/v2/jobs/"+job.ID+"/cancel", testToken, "")
	if resp.StatusCode != http.StatusOK || !strings.Contains(body, `"cancelled"`) {
		t.Fatalf("cancel: %d %s", resp.StatusCode, body)
	}
	resp, body = do(t, "POST", srv.URL+"/v2/jobs/"+job.ID+"/cancel", testToken, "{}")
	if resp.StatusCode != http.StatusConflict || errorCode(t, body) != "failed_precondition" {
		t.Fatalf("second cancel: %d %s", resp.StatusCode, body)
	}
}

func TestCreateValidation(t *testing.T) {
	srv, _ := newTestServer(t, 10)
	for _, body := range []string{
		`{"command": [], "timeout": "5s"}`,
		`{"command": ["true"]}`,
		`{"command": ["true"], "timeout": "0s"}`,
		`{"command": ["true"], "timeout": "61m"}`,
		`{"command": ["true"], "timeout": 5}`,
		`{"command": ["true"], "timeout_seconds": 5}`,
		`not json`,
	} {
		resp, got := do(t, "POST", srv.URL+"/v2/jobs", testToken, body)
		if resp.StatusCode != http.StatusBadRequest || errorCode(t, got) != "invalid_argument" {
			t.Errorf("%s: %d %s", body, resp.StatusCode, got)
		}
	}
}

func TestPages(t *testing.T) {
	srv, _ := newTestServer(t, 10)
	for i := 0; i < 4; i++ {
		do(t, "POST", srv.URL+"/v2/jobs", testToken, `{"command": ["true"], "timeout": "5s"}`)
	}
	var page pageJSON
	_, body := do(t, "GET", srv.URL+"/v2/jobs?page_size=2", testToken, "")
	json.Unmarshal([]byte(body), &page)
	if len(page.Jobs) != 2 || page.NextPageToken == "" {
		t.Fatalf("page 1: %s", body)
	}
	_, body = do(t, "GET", srv.URL+"/v2/jobs?page_size=2&page_token="+page.NextPageToken, testToken, "")
	page = pageJSON{}
	json.Unmarshal([]byte(body), &page)
	if len(page.Jobs) != 2 || page.NextPageToken != "" {
		t.Fatalf("page 2: %s", body)
	}
	for _, q := range []string{"page_size=0", "page_size=201", "page_size=x", "page_token=bogus"} {
		resp, _ := do(t, "GET", srv.URL+"/v2/jobs?"+q, testToken, "")
		if resp.StatusCode != http.StatusBadRequest {
			t.Errorf("%s: status %d", q, resp.StatusCode)
		}
	}
}

func TestAuthAndErrors(t *testing.T) {
	srv, _ := newTestServer(t, 1)
	resp, body := do(t, "GET", srv.URL+"/v2/jobs", "", "")
	if resp.StatusCode != http.StatusUnauthorized || errorCode(t, body) != "unauthenticated" {
		t.Fatalf("no token: %d %s", resp.StatusCode, body)
	}
	resp, _ = do(t, "GET", srv.URL+"/v2/jobs", "wrong", "")
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("wrong token: %d", resp.StatusCode)
	}
	do(t, "POST", srv.URL+"/v2/jobs", testToken, `{"command": ["true"], "timeout": "5s"}`)
	resp, body = do(t, "POST", srv.URL+"/v2/jobs", testToken, `{"command": ["true"], "timeout": "5s"}`)
	if resp.StatusCode != http.StatusTooManyRequests || errorCode(t, body) != "resource_exhausted" {
		t.Fatalf("queue full: %d %s", resp.StatusCode, body)
	}
	resp, body = do(t, "GET", srv.URL+"/v2/jobs/j-missing", testToken, "")
	if resp.StatusCode != http.StatusNotFound || errorCode(t, body) != "not_found" {
		t.Fatalf("unknown job: %d %s", resp.StatusCode, body)
	}
	for _, path := range []string{"/v1/jobs", "/healthz", "/metrics"} {
		resp, _ = do(t, "GET", srv.URL+path, testToken, "")
		if resp.StatusCode != http.StatusNotFound {
			t.Errorf("%s: status %d", path, resp.StatusCode)
		}
	}
}

func TestProbes(t *testing.T) {
	srv, s := newTestServer(t, 10)
	for _, path := range []string{"/livez", "/readyz"} {
		if resp, _ := do(t, "GET", srv.URL+path, "", ""); resp.StatusCode != http.StatusOK {
			t.Fatalf("%s: %d", path, resp.StatusCode)
		}
	}
	s.StartDrain()
	if resp, _ := do(t, "GET", srv.URL+"/readyz", "", ""); resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("readyz while draining: %d", resp.StatusCode)
	}
	if resp, _ := do(t, "GET", srv.URL+"/livez", "", ""); resp.StatusCode != http.StatusOK {
		t.Fatalf("livez while draining: %d", resp.StatusCode)
	}
}
