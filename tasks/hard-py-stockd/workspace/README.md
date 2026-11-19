# stockd

`stockd` keeps the stock of our warehouses. It is event-sourced: each command
that changes the stock writes one or more events to an append-only event log.
The service keeps the current stock in memory (the projection) and writes
snapshots of it. Python 3.11 or later, standard library only.

```sh
python3 -m stockd --data DIR apply commands.jsonl   # or "-" for stdin
python3 -m stockd --data DIR report [--json] [--warehouse WH-1]
python3 -m stockd --data DIR snapshot
python3 -m stockd --data DIR compact
python3 -m stockd --data DIR replay [--json]        # state from all events, snapshots ignored
python3 -m stockd --data DIR check-log
python3 -m unittest                                 # tests
```

Global options: `--data DIR` (default `./data`), `--segment-bytes N` (the
segment size limit, see below), `--log-level`. Each call of the command is one
process: it loads the state from the data directory (recovery), does its work
and stops. In production the terminal gateway runs `apply` for each batch of
commands, and the job `stockd-nightly` runs `snapshot` and then `compact` at
01:30.

## Data directory

| Path | Content |
|---|---|
| `stockd.toml` | Optional settings: `segment_max_bytes` (default 65536), `snapshot_keep` (2), `request_window` (5000), `max_receive_lines` (50). `--segment-bytes` replaces `segment_max_bytes` |
| `catalog.json` | Optional pack sizes: `{"skus": {"BOLT-M8": {"pack": 100}}}` |
| `segments/<first seq>.seg` | The event log. One JSON event on each line. Sequence numbers start at 1 and are continuous over all segments |
| `snapshots/snap-<seq>.json` | Snapshots. `<seq>` is the last event that the snapshot contains |

- The event log is the source of truth. Events always store units, never packs.
- When the active segment has `segment_max_bytes` bytes or more, the store
  closes it before the next event and starts a new segment. The service writes
  a snapshot each time a segment is closed. It keeps the newest
  `snapshot_keep` snapshots.
- Recovery loads the newest snapshot that it can read and replays only the
  events after it. If a snapshot cannot be read, it uses the next older one.
- `compact` removes each closed segment whose events are all contained in the
  newest snapshot. After `compact` the old events are gone, so only the
  snapshot has them.
- A crash can leave a partial last line in the active segment. The store
  removes it when it opens the log.
- Lines without `"v"` are events of version 1 (before 2026-03). They are
  converted when they are read.

## Commands

`apply` reads one JSON object per line and prints one result line per command,
in the same order. A command can have a `request_id` (a non-empty string).

| `op` | Fields | Events |
|---|---|---|
| `receive` | `warehouse`, `lines`: list of `{"sku", "qty"}` or `{"sku", "packs"}` (1 to `max_receive_lines` lines) | one `Received` for each line |
| `adjust` | `warehouse`, `sku`, `delta` (not 0), `reason` | `Adjusted` |
| `reserve` | `warehouse`, `sku`, `qty`, `order` | `Reserved` |
| `release` | `reservation` | `Released` |
| `ship` | `reservation` | `Shipped` (removes the reserved quantity from the stock) |
| `transfer` | `from`, `to`, `sku`, `qty` | `TransferredOut`, then `TransferredIn` |

Rules:

- `reserve` and `transfer` need `available` (on hand minus reserved) of at
  least `qty` in the source warehouse. `adjust` must not make on hand less than
  reserved.
- Reservation numbers and transfer numbers start at 1 and increase by 1 for
  each applied `reserve` or `transfer`.
- `release` of a reservation that is not open (unknown, released or shipped)
  is not an error: the result is `ignored`. `ship` of a reservation that is
  not open is `rejected`.
- Request IDs: when a command has a `request_id` of an applied command, the
  service does not apply it again and the result is `duplicate`. The service
  remembers the request IDs of the last `request_window` applied commands.
  Rejected and ignored commands are not remembered, so a client can send them
  again.

Result lines (keys sorted):

| `status` | Other keys |
|---|---|
| `applied` | `request_id`, `seq` (the last event of the command), `reservation` for `reserve`, `transfer` for `transfer` |
| `duplicate` | `request_id` |
| `ignored` | `request_id` |
| `rejected` | `request_id`, `error` |

## Reports

`report` prints a table with the columns `WAREHOUSE SKU ON_HAND RESERVED
AVAILABLE`, one row for each warehouse and SKU that has events, sorted by
warehouse and SKU, then the line `<n> open reservation(s)`.

`report --json` prints `{"levels": [...], "reservations": [...]}`. Each level
is `{"warehouse", "sku", "on_hand", "reserved", "available"}` in the order of
the table. Each open reservation is `{"id", "warehouse", "sku", "qty",
"order"}` (`id` is the reservation number), sorted by warehouse, SKU and order.

`replay` prints the same report, but builds the state from all events in the
log and ignores the snapshots. It fails after `compact` has removed segments.
