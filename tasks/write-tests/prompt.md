The `window` package (maintenance windows for our node drain job) has no tests, and we plan to refactor it soon. Please write unit tests for it in `window/window_test.go`.

The documented behavior is in the package and function comments of `window/window.go`. As far as we know the code is correct, so do not change `window.go` or the other files; only add tests. The tests must pass on the current code with `go test ./...`.

The tests are our safety net for the refactor, so they must catch a change in any documented behavior, including the edge cases. Use only the standard library.
