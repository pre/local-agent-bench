# Retention planner

`keepr` reads a list of backup snapshots and a retention policy. It decides which snapshots to keep and which to remove, and prints the plan. It does not remove anything.

## Files

Snapshot list: one snapshot on each line. `#` starts a comment.

```
<id> <time> host=<host> paths=<path>[,<path>...] [tags=<tag>[,<tag>...]]
```

- `<id>` is a hexadecimal text, unique in the list.
- `<time>` is `YYYY-MM-DDTHH:MM:SS` with `Z` or an offset such as `+02:00`.
- Paths and tags are sets: `input.rs` sorts them and removes duplicates.

Policy file: one `key = value` on each line. `#` starts a comment.

| Key | Value |
|---|---|
| `keep-last`, `keep-hourly`, `keep-daily`, `keep-weekly`, `keep-monthly`, `keep-yearly` | a count: 0 or more, or -1 for no limit |
| `keep-within`, `keep-within-daily` | a span such as `1y2m3d4h` (years, months, days, hours; each part is optional, the order is fixed) |
| `keep-tag` | a tag. The key can occur more than once |
| `group-by` | a comma list of `host`, `paths`, `tags`, or `none`. Default `host,paths` |
| `timezone` | `+HH:MM`, `-HH:MM` or `Z`. Default `Z` |

The parsers in `src/input.rs` and the time functions in `src/time.rs` are complete.

## Rules

The function `keepr::plan(snapshots, policy)` makes the plan. The function `keepr::render(plan, snapshots, policy)` gives its text.

R1. Empty policy. A rule is active when its count is set and is not 0, or when its span is set (also a span of 0), or when the policy has at least one `keep-tag`. If no rule is active, `plan` gives `PlanError::EmptyPolicy`. This prevents the removal of all snapshots by an empty or wrong policy file.

R2. Groups. The snapshots go into groups by the fields of `group-by`: two snapshots are in the same group when they have the same value of each of these fields (the host; the set of paths; the set of tags). With `group-by = none` there is one group with all snapshots. The rules R5 to R10 apply to each group separately. The groups are sorted by their values: first the host, then the paths joined with `,`, then the tags joined with `,`. Only the fields of `group-by` count. Texts compare by bytes.

R3. Order in a group. The snapshots of a group are sorted from the newest to the oldest. When two snapshots have the same time, the snapshot with the greater id (by bytes) counts as the newer one. "Newest" and "previous" in the rules below use this order.

R4. Local time. The hour, the day, the week, the month and the year of a snapshot are those of its time at the offset `timezone` of the policy. The time in the snapshot list does not change this. The time zone has a fixed offset, so there is no daylight saving time.

R5. `keep-last N` keeps the N newest snapshots. -1 keeps all.

R6. Bucket rules. `keep-hourly`, `keep-daily`, `keep-weekly`, `keep-monthly` and `keep-yearly` put each snapshot in a bucket: its hour (date and hour), its date, its ISO 8601 week, its month (year and month) or its year. ISO weeks start on Monday, and week 1 of a year is the week that contains the first Thursday of that year. Thus 2026-12-31 is in week 53 of 2026, and 2027-01-03 is also in week 53 of 2026. A bucket rule with count N goes through the snapshots from the newest to the oldest. It keeps a snapshot when the snapshot is in a different bucket than the snapshot that the rule kept before (the first snapshot is always kept), until the rule has kept N snapshots. -1 means no limit. Thus the rule keeps the newest snapshot of each of the N newest buckets that contain snapshots.

R7. `keep-within S`. Take the newest snapshot of the group and its local date and time. Subtract S from it in this order: the years (a 29 February becomes 28 February when the year is not a leap year), then the months (when the day is not in the month, it becomes the last day of that month), then the days, then the hours. The result is the cutoff. The rule keeps each snapshot whose time is at the cutoff or after it. Example: newest 2024-03-31T10:00 local, `keep-within = 1m1d` gives 2024-02-29T10:00, then 2024-02-28T10:00.

R8. `keep-within-daily S`. The cutoff is the same as in R7. From the snapshots at or after the cutoff, the rule keeps the newest snapshot of each local date.

R9. `keep-tag T`. The rule keeps each snapshot that has at least one of the tags of the `keep-tag` lines.

R10. Safety. When no rule keeps any snapshot of a group, the newest snapshot of that group is kept, with the reason `safety`.

R11. Reasons. A kept snapshot has the reasons of all rules that keep it, each one once, in this order: `last`, `hourly`, `daily`, `weekly`, `monthly`, `yearly`, `within`, `within-daily`, `tag`, `safety`. A snapshot without a reason is removed. The rules are independent: each rule examines all snapshots of the group, also the snapshots that other rules keep.

R12. Output of `render`. For each group, in the order of R2:
  - A header line: `group` and then ` host=<host>`, ` paths=<paths joined with ,>` and ` tags=<tags joined with ,>`, only for the fields of `group-by`, in this order. An empty tag set gives `tags=`. With `group-by = none` the header is `group *`.
  - One line for each snapshot of the group, in the order of R3: `keep <id> <time> <reasons joined with ,>` or `remove <id> <time>`. The time is in the format of the snapshot list, at the offset of the policy (`Z` when the offset is 0).
  - An empty line.

  The last line is `kept <K>, removed <R>` with the counts of all groups.
