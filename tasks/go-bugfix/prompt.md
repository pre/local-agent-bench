The `dur` command in this repository adds durations and prints the total. Users report two problems:

- `go run ./cmd/dur 1w2d` fails with "units out of order", but `1w2d` is a valid duration.
- `go run ./cmd/dur 1.05h` prints `1h30m`. The correct total is `1h3m`.

Find the causes and correct them. The accepted format is in the package documentation of `duration` (`duration/doc.go`). Other inputs can have the same causes, so correct the causes, not only the two examples.

Do not change the module path or the exported API of package `duration`. The project uses only the Go standard library and there is no network access.
