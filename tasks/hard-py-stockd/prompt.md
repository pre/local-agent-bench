After the nightly maintenance and the restart of `stockd` on 17 November, the stock report of the morning did not agree with the physical counts. The service log of the day before, the night and the morning is in `incident/stockd.log`. The results of the first batch of the morning are in `incident/morning-results.jsonl`, and a copy of the data directory after that batch is in `incident/data`. See `README.md` for how the service works.

What the warehouse team found at 08:15 on 17 November:

1. WH-1 has 154 VALVE-22 on hand in the report, but the count is 130. Yesterday evening transfer `trf-0412` moved 24 VALVE-22 from WH-1 to WH-2. WH-2 shows the 24 units, but WH-1 did not go down.
2. The goods receipt terminal sent delivery `rcv-881` (4 packs of BOLT-M8) again after a timeout during the restart. It has the same request ID as yesterday, but the result was `applied`, not `duplicate`. WH-1 now shows 1483 BOLT-M8 instead of 1083.

The team also found other values in the report that do not agree with the counts, and they could not explain them yet.

The unit tests pass, and `replay` cannot help because `compact` removed the old segments.

Please find the root causes and fix them in the code. Requirements:

- A restart at any point must not change anything: for each sequence of commands, the results of the commands and the state (`report --json`) must be the same as with one process that does not restart. This includes restarts after `snapshot` and `compact`, and segment sizes of any value. The problems above are examples, not the complete list of cases.
- Recovery must continue to load the newest snapshot and replay only the events after it, and `compact` must continue to remove the segments that the newest snapshot contains.
- Data directories that the current version wrote (segments and snapshots) must continue to load, and give the correct state for the events and snapshots that they contain.
- Do not change the command line, the command and result formats or the report formats in `README.md`.
- `python3 -m unittest` must pass. Add tests for the causes that you find.

You do not have to repair the files in `incident/data`.
