For capacity planning I need a per-rack view in `nodeinv`. Please add a boolean flag `-by-rack`. With it, `nodeinv` prints one row per rack instead of one row per node, and a TOTAL row at the end:

```
$ go run ./cmd/nodeinv -f testdata/nodes.inv -by-rack
RACK   NODES  READY  GPUS  FREE
r01    4      3      32    11
r02    3      1      24    6
TOTAL  7      4      56    17
```

- NODES is the number of nodes, READY the number of nodes in state `ready`, GPUS the sum of all GPUs in the rack.
- FREE is the sum of the GPUs that are not used, counted only on `ready` nodes. Drained and down nodes have no free GPUs.
- Racks are sorted by name. The existing filters `-state` and `-rack` apply first, so the counts include only the selected nodes.
- With `-o json`, print a JSON array with one object per rack and the keys `rack`, `nodes`, `ready`, `gpus` and `free` (integers, no TOTAL object). If no node is selected, the table has only the header and a TOTAL row with zeros, and the JSON output is `[]`.

Without `-by-rack` the output must stay as it is now. Please keep the structure of the code (flags in `internal/cli`, counting in `internal/inventory`, formatting in `internal/output`) and add tests.
