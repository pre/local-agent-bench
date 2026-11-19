Our spreadsheet engine does not work with the new planning sheet. This command prints a few lines and then runs for hours, and the memory use grows to gigabytes:

```
$ go run ./cmd/sheetcalc -watch E1,F1 testdata/plan.sheet testdata/plan.edits
```

There are more problems. The watchers report values that the sheet never has at the end of an update: `go run ./cmd/sheetcalc -watch B3,C1 testdata/small.sheet testdata/small.edits` shows two changes of B3 in update 2. And `Apply` does not make its edits as one update.

`docs/ENGINE.md` specifies the update rules U1 to U10. The engine does not follow them. Change the code so that it follows all of these rules. Keep the public API of the packages `engine` and `value`, the formula language and the evaluation rules as they are. When you are done, `go test ./...` must pass and the two commands above must finish.
