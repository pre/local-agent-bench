The counters of our job dispatcher (`dispatch` package) are wrong under load. Our metrics exporter calls `Stats()` every few hundred microseconds while jobs run, and the dashboard shows numbers that do not add up: the per-node counters often do not match the totals of the same snapshot, and after `Close()` the `Retried` total is lower than the number of retries that the jobs themselves count. With a light load everything looks correct.

You can see it with the load generator:

```
$ go run ./cmd/loadgen
dispatcher: submitted=20000 succeeded=15000 failed=5000 retried=24952
jobs:       attempts=45000 failed attempts=30000 retries=25000
exporter:   snapshots that do not add up: 124
```

Please find the cause and fix it, so that the counters are correct under any load and the numbers in one `Stats()` snapshot always add up. Keep the exported API of the package (types, fields and method signatures) as it is.
