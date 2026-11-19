// Command jobq-server serves the job queue API (contract version 2).
package main

import (
	"context"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"example.internal/jobq/internal/api"
	"example.internal/jobq/internal/config"
	"example.internal/jobq/internal/metrics"
	"example.internal/jobq/internal/store"
)

const shutdownTimeout = 10 * time.Second

func main() {
	log.SetFlags(0)
	log.SetPrefix("jobq-server: ")

	cfg, err := config.FromEnv(os.Getenv)
	if err != nil {
		log.Print(err)
		os.Exit(2)
	}
	token, err := config.ReadToken(cfg.TokenFile)
	if err != nil {
		log.Print(err)
		os.Exit(2)
	}

	st := store.New(cfg.QueueLimit)
	reg := metrics.New()
	reg.Gauge("jobq_jobs_queued", "Jobs in the state queued.", func() float64 {
		return float64(st.QueuedCount())
	})
	apiServer := api.New(cfg, token, st, reg)

	metricsMux := http.NewServeMux()
	metricsMux.Handle("GET /metrics", reg.Handler())

	servers := []*http.Server{
		{Addr: cfg.APIAddr, Handler: apiServer.Handler(), ReadHeaderTimeout: 10 * time.Second},
		{Addr: cfg.MetricsAddr, Handler: metricsMux, ReadHeaderTimeout: 10 * time.Second},
	}
	errc := make(chan error, len(servers))
	for _, srv := range servers {
		ln, err := net.Listen("tcp", srv.Addr)
		if err != nil {
			log.Print(err)
			os.Exit(1)
		}
		log.Printf("listening on %s", ln.Addr())
		go func() { errc <- srv.Serve(ln) }()
	}

	sigc := make(chan os.Signal, 1)
	signal.Notify(sigc, syscall.SIGTERM, syscall.SIGINT)

	select {
	case err := <-errc:
		log.Print(err)
		os.Exit(1)
	case sig := <-sigc:
		log.Printf("%v: draining for %v", sig, cfg.DrainDelay)
	}
	apiServer.StartDrain()
	time.Sleep(cfg.DrainDelay)

	ctx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()
	for _, srv := range servers {
		if err := srv.Shutdown(ctx); err != nil {
			log.Print(err)
		}
	}
	log.Print("stopped")
}
