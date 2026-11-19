# sheet

A small spreadsheet engine and a command line front end.

```
go run ./cmd/sheetcalc -watch B3,C1 testdata/small.sheet testdata/small.edits
go run ./cmd/sheetcalc -all testdata/small.sheet
go test ./...
```

- `docs/ENGINE.md`: the cells, the formula language, the API and the update rules.
- `value/`: cell values.
- `engine/`: the sheet and its updates.
- `internal/addr`, `internal/formula`, `internal/eval`: addresses, the formula parser and the evaluator.
- `internal/sheetfile`: the file formats of `cmd/sheetcalc`.
