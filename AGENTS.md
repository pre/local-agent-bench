# Agent instructions

## Documentation

`README.md` is the entry point. It holds only the purpose of the harness, the `just` commands, the parts of the repository and the "Documentation" table.

Record each explanation and each decision in `docs/`, one subject in each file:

- If a file in `docs/` has the subject, change that file. If not, make a new file and add a row for it to the "Documentation" table of `README.md`.
- Write a decision with its reason. A decision that qualifies for an ADR goes into `docs/adr/`, see "Architecture decision records".
- When `README.md` must refer to a subject, write one sentence and a link to its file in `docs/`.

## Architecture decision records

`docs/adr/` records the decisions that later agents must know, with the reason for each. Read the ADRs before you change the architecture.

Write an ADR only when the decision has all three properties:

1. It is hard to reverse.
2. A reader of the code finds it surprising without the context.
3. It is the result of a real trade-off between alternatives.

A decision that a later change can easily reverse does not get an ADR. Record it in the file of its subject in `docs/`.

### Format

File name: `docs/adr/NNNN-slug.md`. `NNNN` is the highest number in `docs/adr/` plus one. The "Documentation" table of `README.md` has one row for `docs/adr/`, and an ADR does not get a row of its own.

```md
# Short title of the decision

Status: accepted.

One to three sentences: the context, the decision and the reason.
```

Add these sections only when they give the reader information that the code does not give:

- `## Decision`: a list, when the decision has several parts.
- `## Considered Options`: the rejected alternatives and the reason for each rejection.
- `## Consequences`: effects of the decision that are not obvious.

### Change a decision

Write a new ADR. Do not change the decision text of the old ADR. Write the relation in the `Status` line of the two ADRs:

- New ADR: `Status: accepted. Supersedes ADR 0003 for the result files.` Use `Extends` or `Changes` when the old decision stays partly true.
- Old ADR: `Status: superseded by ADR 0008 for the result files.` Or, when the old decision stays true: `Status: accepted. ADR 0008 moves the server values to run.json.`

When a file in `docs/`, a README or a code comment depends on a decision, refer to it as `ADR NNNN`.
