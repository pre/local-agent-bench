`minisql` runs simple SELECT queries on CSV tables. Version 1 is in this repository. For version 2 we need `SELECT DISTINCT`, `GROUP BY`, `HAVING` and the aggregate functions `COUNT`, `SUM`, `AVG`, `MIN` and `MAX`.

`docs/SQL.md` is the specification. The section "Grouping and aggregates" (rules G1 to G11) describes version 2, and the other sections describe the behavior that already exists. Implement version 2 so that the engine follows the whole specification. All the behavior of version 1 must stay as it is, and the public API of the package `db` must not change. Do not add dependencies (the build has no network).

Example:

```
$ go run ./cmd/minisql "SELECT region, COUNT(*) AS n, SUM(qty * price) AS revenue FROM sales GROUP BY region HAVING COUNT(*) > 1 ORDER BY revenue DESC"
```

When you are done, `go test ./...` must pass.
