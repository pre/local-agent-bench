// Command loadgen puts synthetic load on a dispatcher and prints the
// counters of the dispatcher next to the counters of the jobs themselves.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"example.com/jobrunner/dispatch"
)

func main() {
	jobs := flag.Int("jobs", 20000, "number of jobs")
	producers := flag.Int("producers", 8, "number of goroutines that submit jobs")
	workers := flag.Int("workers", 16, "number of workers")
	retries := flag.Int("retries", 2, "maximum number of retries of a job")
	flag.Parse()

	d := dispatch.New(dispatch.Options{Workers: *workers, MaxRetries: *retries})

	var attempts, failures atomic.Int64
	errFlaky := errors.New("flaky")

	// The metrics exporter reads the counters while the jobs run. In one
	// snapshot the counters of the nodes must add up to the totals.
	stop := make(chan struct{})
	inconsistent := make(chan int)
	go func() {
		bad := 0
		for {
			select {
			case <-stop:
				inconsistent <- bad
				return
			case <-time.After(200 * time.Microsecond):
			}
			s := d.Stats()
			var succeeded, failed, retried int
			for _, ns := range s.PerNode {
				succeeded += ns.Succeeded
				failed += ns.Failed
				retried += ns.Retried
			}
			if succeeded != s.Succeeded || failed != s.Failed || retried != s.Retried {
				bad++
			}
		}
	}()

	var wg sync.WaitGroup
	for p := range *producers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := p; i < *jobs; i += *producers {
				failFirst := int64(i % 4)
				var tries atomic.Int64
				job := dispatch.Job{
					ID:   fmt.Sprintf("job-%d", i),
					Node: fmt.Sprintf("node-%02d", i%12),
					Run: func(ctx context.Context) error {
						attempts.Add(1)
						if tries.Add(1) <= failFirst {
							failures.Add(1)
							return errFlaky
						}
						return nil
					},
				}
				if err := d.Submit(job); err != nil {
					fmt.Fprintln(os.Stderr, err)
					os.Exit(1)
				}
			}
		}()
	}
	wg.Wait()
	d.Close()
	close(stop)
	bad := <-inconsistent

	s := d.Stats()
	fmt.Printf("dispatcher: submitted=%d succeeded=%d failed=%d retried=%d\n", s.Submitted, s.Succeeded, s.Failed, s.Retried)
	fmt.Printf("jobs:       attempts=%d failed attempts=%d retries=%d\n", attempts.Load(), failures.Load(), attempts.Load()-int64(*jobs))
	fmt.Printf("exporter:   snapshots that do not add up: %d\n", bad)
}
