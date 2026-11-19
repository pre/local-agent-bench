# Sheet engine

The package `engine` keeps the cells of a sheet and their values. The package `value` has the cell values. `cmd/sheetcalc` is a command line front end.

## Cells and inputs

A cell has an address such as `B7` (column letters, row number, not case sensitive). The input of a cell is a text:

| Input | Meaning |
|---|---|
| `""` | The cell is empty. `Set(cell, "")` clears a cell |
| starts with `=` | A formula, see "Formulas" |
| starts with `'` | A text: the input without the apostrophe |
| a number, for example `12`, `-0.5`, `2.5e3` | A number. Spaces around it are permitted |
| `TRUE`, `FALSE` (not case sensitive) | A bool |
| other text | A text |

An empty cell has the empty value (`value.Empty`).

## Formulas

- Literals: numbers, texts in double quotes (`""` is a quote in a text), `TRUE`, `FALSE`.
- References: `A1` is the value of one cell. `A1:B3` is a range. A range is permitted only as a direct argument of a function. A range can be very large: `A1:A1048576` is all of column A, and `A1:XFD1048576` is the full sheet.
- Operators, from the weakest to the strongest binding: comparisons `= <> < <= > >=`, then `&` (join texts), then `+ -`, then `* /`, then `^` (right associative), then the prefix operators `-` and `+`. Thus `-2^2` is 4.
- Functions: `IF(cond, then [, else])`, `AND`, `OR`, `NOT`, `SUM`, `MIN`, `MAX`, `AVERAGE`, `COUNT`, `ABS`, `ROUND(x, digits)`, and the custom functions of `RegisterFunc`. Function names are not case sensitive.
- `IF` evaluates the condition, and then only the selected branch. All other functions evaluate all their arguments from left to right. A range argument reads each cell of the range, by row, then by column.
- Errors are values: `#DIV/0!`, `#VALUE!`, `#NAME?` (unknown function), `#NUM!` (a result that is not a finite number). An error operand gives the error as the result.

The package `internal/eval` has the exact conversion rules.

## API

```go
func New() *Sheet
func (s *Sheet) Set(cell, input string) error
func (s *Sheet) Apply(edits []Edit) error
func (s *Sheet) Value(cell string) value.Value
func (s *Sheet) Input(cell string) string
func (s *Sheet) Cells() []string
func (s *Sheet) Watch(cell string, fn WatchFunc) error
func (s *Sheet) RegisterFunc(name string, fn Func) error
```

The errors are `ErrAddress`, `ErrSyntax`, `ErrCycle` and `ErrFuncName`. Callers examine them with `errors.Is`.

A custom function is called each time a formula that calls it is evaluated, with the values of its arguments. Custom functions can have side effects (for example, they can count their calls). The tests of the engine use this to count evaluations.

## Updates

An update is one call of `Set` or `Apply`. These rules apply to each update.

U1. One update. `Set(c, x)` is the same as `Apply([]Edit{{c, x}})`. `Apply` makes all its edits in one update. When an `Apply` has more than one edit for a cell, the last edit of that cell applies.

U2. No partial updates. If an edit has an invalid address or a formula with a syntax error, or if the inputs after the update make a cycle (U8), the update returns an error and changes nothing: inputs, values and the data for U5 stay as they were, and no watcher is called.

U3. Reads. The reads of a formula cell are the cells that its most recent evaluation read (see "Formulas": only the selected branch of `IF`, each cell of a range, also the empty cells of a range). The reads can change from one evaluation to the next. A read of an empty cell is also a read.

U4. At most once. In one update, the engine evaluates each formula cell at most once.

U5. Only when necessary. In one update, the engine evaluates a formula cell if and only if:
  - (a) the update sets the input of that cell to a formula, or
  - (b) at least one cell in its reads (U3) has a different value at the end of the update than at the start of the update.

  "Different" uses `value.Value.Equal`. The engine does not evaluate any other formula. Thus a formula whose result does not change stops the update of the formulas that read it.

U6. Consistent reads. When the engine evaluates a formula, each cell that the formula reads already has its value for the end of the update.

U7. Watchers. After all evaluations of an update, the engine calls the watchers of each watched cell whose value at the end of the update is different from its value at the start. It calls each watcher once with the address of the cell (upper case, for example `B7`), the value at the start and the value at the end. It calls the watchers of the cells in the order of the cells by row, then by column, and the watchers of one cell in the order of the `Watch` calls. A watcher must not call `Set` or `Apply`.

U8. Cycles. A formula must not refer to its own cell, directly or through other formulas. For this rule, a formula refers to each cell in its text: each single reference, each cell of each range, and the references in both branches of `IF`. An update that makes a cycle returns an error that wraps `ErrCycle`.

U9. Cost. Except for the cycle check of new formulas (U8), the time of an update grows with the number of edits, the number of cells that refer to an edited cell (directly or through other formulas), the size of their formulas, and the number of formulas in the sheet that have a range. It does not grow with the number of other cells in the sheet.

U10. Large ranges. A sheet can have thousands of formulas with ranges such as `SUM(A1:A1048576)`. The time and the memory of an update (also of its cycle check) must not grow with the number of empty cells in the ranges of the formulas. The size of a formula is the length of its text, not the number of cells in its ranges. The built-in functions `SUM`, `MIN`, `MAX`, `AVERAGE` and `COUNT` ignore the empty cells of a range, so their evaluation also must not grow with the number of empty cells in the range. The only exception is a custom function with a range argument: it gets the values of all cells of the range (see "Formulas").
