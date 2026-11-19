// Command jobq-server serves the job queue API.
package main

import (
	"context"
	"errors"
	"fmt"
	"log"
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

	st := store.New(cfg.QueueLimit)
	reg := metrics.New()
	reg.Gauge("jobq_jobs_queued", "Jobs in the state queued.", func() float64 {
		return float64(st.QueuedCount())
	})

	srv := &http.Server{
		Addr:              fmt.Sprintf(":%d", cfg.Port),
		Handler:           api.New(cfg, st, reg).Handler(),
		ReadHeaderTimeout: 10 * time.Second,
	}

	errc := make(chan error, 1)
	go func() {
		log.Printf("listening on %s", srv.Addr)
		errc <- srv.ListenAndServe()
	}()

	sigc := make(chan os.Signal, 1)
	signal.Notify(sigc, syscall.SIGTERM, syscall.SIGINT)

	select {
	case err := <-errc:
		log.Print(err)
		os.Exit(1)
	case sig := <-sigc:
		log.Printf("%v: shutting down", sig)
	}

	ctx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Print(err)
		os.Exit(1)
	}
}
