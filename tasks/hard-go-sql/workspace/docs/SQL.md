# The SQL dialect of minisql

minisql runs one `SELECT` statement on one table. Tables come from CSV files (see `table/table.go`). Keywords and column names are not case sensitive. Text values are case sensitive.

## Statement

```
SELECT [DISTINCT] item, ...
FROM table
[WHERE condition]
[GROUP BY expr, ...]
[HAVING condition]
[ORDER BY expr [ASC|DESC], ...]
[LIMIT n [OFFSET m]]
```

`item` is `*` (all columns of the table, in table order) or `expr [[AS] alias]`.

Version 1 does not have `DISTINCT`, `GROUP BY`, `HAVING` and the aggregate functions. They give the error code `unsupported`. Version 2 adds them: see "Grouping and aggregates".

## Types and values

`INT` (64 bits), `FLOAT` (64 bits), `TEXT`, `BOOL` and `NULL`. The literal `NULL` has no type. A column can contain NULL.

Output format (`value.Value.String`): `NULL`, INT in decimal, FLOAT with 1 to 6 digits after the point (rounded, trailing zeros removed: `2.5`, `3.0`, `0.333333`), TEXT as is, `TRUE`, `FALSE`.

## Expressions

Precedence from the weakest: `OR`, `AND`, `NOT`, comparisons (`= <> != < <= > >=`) and `IS [NOT] NULL`, `||`, `+ -`, `* / %`, unary `-`.

- Arithmetic needs numbers. INT with INT gives INT, else FLOAT. `/` of two INTs truncates toward zero. `%` needs INTs. An INT result that does not fit in 64 bits gives the error `overflow`. A division by zero gives the error `division_by_zero`.
- Comparisons need two numbers (INT and FLOAT compare by value), two TEXTs (byte order) or two BOOLs (FALSE < TRUE).
- `||` joins two TEXTs.
- NULL: an operator with a NULL operand gives NULL, except `IS NULL`, `IS NOT NULL` and the three-valued logic of `AND` and `OR` (`FALSE AND NULL` is FALSE, `TRUE OR NULL` is TRUE).
- Scalar functions: `LOWER(t)`, `UPPER(t)`, `LENGTH(t)` (characters), `ABS(n)`, `ROUND(n [, digits])` (FLOAT), `COALESCE(x, ...)` (the first argument that is not NULL).
- `WHERE` keeps the rows where the condition is TRUE (not FALSE, not NULL).

The canonical text of an expression (`sql.Expr.String`) is also the name of an output column without alias. Function names are upper case, operands that are operator expressions are in parentheses, text literals are in single quotes: `price * qty`, `(price * qty) + 1`, `LOWER(region)`. A plain column has the name of its declaration in the table.

## ORDER BY, LIMIT, OFFSET

- An `ORDER BY` item is an INT literal (the number of an output column, from 1; another number gives the error `ordinal`), a plain name that is the alias of an output column (the alias wins over a table column with the same name), or another expression.
- NULL comes before all other values. `DESC` reverses the order. The sort is stable: rows with equal keys keep their order.
- `OFFSET m` skips the first m rows, then `LIMIT n` keeps at most n rows.

## Errors

Each failed query gives an error of type `*db.Error` with a `Code`:

| Code | When |
|---|---|
| `syntax` | The text does not parse |
| `unsupported` | A feature that this version does not have |
| `unknown_table`, `unknown_column`, `unknown_function` | A name that does not exist |
| `type` | An operand or argument with a wrong type |
| `ordinal` | An output column number out of range |
| `overflow`, `division_by_zero` | Arithmetic errors while the query runs |
| `grouping` | See G5 |
| `aggregate` | See G6 |
| `distinct` | See G10 |

## Grouping and aggregates

This section is version 2. It is not implemented yet.

Aggregate functions: `COUNT(*)`, `COUNT(x)`, `SUM(x)`, `AVG(x)`, `MIN(x)`, `MAX(x)`. Each of them, except `COUNT(*)`, also has the form `F(DISTINCT x)`. The canonical text of these calls is `COUNT(*)`, `SUM(x)` and `COUNT(DISTINCT x)` (with the canonical text of `x`).

G1. Aggregate query. A query is an aggregate query when it has `GROUP BY` or `HAVING`, or when its select list or its `ORDER BY` has an aggregate function.

G2. Groups. The rows that `WHERE` keeps go into groups. Two rows are in the same group when their values of each `GROUP BY` expression are identical. Identical means: two NULLs are identical, and other values are identical when they compare as equal (thus `0.0` and `-0.0` are identical). An aggregate query without `GROUP BY` has exactly one group that has all rows, also when there are no rows. An aggregate query with `GROUP BY` and no rows has no groups.

G3. Order of groups. Before `ORDER BY`, the groups are in the order of their first row in the table.

G4. GROUP BY items. A `GROUP BY` item is one of:
  - an INT literal: the number of a select item, from 1 (another number gives the error `ordinal`). The group expression is the expression of that item.
  - a plain name: if the table has a column with that name, the column. Else, if a select item has that alias, the expression of that item. Else the error `unknown_column`. Thus in `GROUP BY` a table column wins over an alias.
  - another expression on the columns of the table.

G5. References after grouping. In an aggregate query, the select list, `HAVING` and `ORDER BY` can contain only: aggregate function calls, group expressions, literals, and operators and scalar functions applied to these. An expression is a group expression when its canonical text is equal to the canonical text of a `GROUP BY` expression; column names are compared without case. For example, with `GROUP BY price * qty` the item `(price * qty) + 1` is valid. A column that is not inside an aggregate function and not inside a group expression gives the error `grouping`. `SELECT *` in an aggregate query is valid only when each column of the table is a group expression.

G6. Aggregate functions in the wrong place. The argument of an aggregate function is an expression on the columns of the table, and it must not contain an aggregate function. An aggregate function in `WHERE`, in `GROUP BY` or inside another aggregate function gives the error `aggregate`. A `GROUP BY` number that refers to a select item with an aggregate function also gives `aggregate`.

G7. Results of the aggregate functions. NULL values of the argument are ignored. With `DISTINCT`, only one of each set of identical values counts.
  - `COUNT(*)`: the number of rows of the group. `COUNT(x)`: the number of values that are not NULL. Type INT, never NULL.
  - `SUM(x)`: x must be a number, else the error `type`. INT for an INT argument, FLOAT for a FLOAT argument. NULL when there are no values. An INT sum is exact: it gives the error `overflow` only when the final sum does not fit in 64 bits, also when the sum of the first rows does not fit. FLOAT values are added in the order of the rows.
  - `AVG(x)`: x must be a number. Type FLOAT. NULL when there are no values. For INT values, the exact sum divided by the count, as the nearest FLOAT. For FLOAT values, the FLOAT sum (in the order of the rows) divided by the count.
  - `MIN(x)`, `MAX(x)`: any type except NULL. The result has the type of x. NULL when there are no values. Numbers, texts and bools compare as in "Expressions".

  The values of a `DISTINCT` aggregate are used in the order of their first row.

G8. HAVING. The condition is computed for each group (it can use aggregate functions that are not in the select list). The groups where it is TRUE stay. A plain name in `HAVING` is a table column, never an alias.

G9. ORDER BY in an aggregate query. The rules of "ORDER BY" apply, and G5 applies to the expressions. `ORDER BY` can use aggregate functions that are not in the select list.

G10. SELECT DISTINCT. After `WHERE`, grouping and `HAVING`, `DISTINCT` removes each output row that is identical to an earlier output row (identical in each column, see G2). The first row of each set stays. Then `ORDER BY` sorts the rows. With `DISTINCT`, each `ORDER BY` item must be an output column: a number, an alias, or an expression with the same canonical text as a select item (column names are compared without case, as in G5). Another item gives the error `distinct`.

G11. LIMIT and OFFSET apply last, after `ORDER BY`.
