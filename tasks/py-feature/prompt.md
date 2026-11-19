Capacity planning asks every week how much CPU, memory and GPU we have per rack, and today somebody adds it up by hand from `nodeinv list`. Please add a `capacity` subcommand to `nodeinv`.

- `python -m nodeinv capacity` prints one row for each group of the selected nodes, then a `TOTAL` row.
- `--by rack|zone|role` selects the grouping attribute. The default is `rack`.
- It takes the same node filters as `list` (`--role`, `--zone`, `--label`, `--include-cordoned`) with the same meaning, so cordoned nodes are not counted unless `--include-cordoned` is given.
- The table uses the same format as `list`. The columns are `<ATTR> NODES CPU MEM_GIB GPU`, where `<ATTR>` is the grouping attribute in upper case (`RACK`, `ZONE` or `ROLE`).
- Groups are sorted by name. A node that has no value for the attribute goes into the group `-`.
- `MEM_GIB` is the total memory of the group (or of all selected nodes for `TOTAL`) in GiB, rounded down to a whole number. `GPU` is the number of GPUs.
- `--json` prints one object instead of the table: `{"by": "rack", "groups": [{"name": "r01", "nodes": 3, "cpu": 288, "mem_gib": 1664, "gpu": 0}, ...], "total": {"nodes": ..., "cpu": ..., "mem_gib": ..., "gpu": ...}}`, with the groups in the same order as the table.
- Put the grouping in a function `summarize_capacity(nodes, by)` in a new module `nodeinv/capacity.py`. It takes a list of `Node` objects and the attribute name, and returns the list of group dicts exactly as in the `groups` part of the JSON. It does no filtering and no total. The dashboard job will import it.

Add tests for the new subcommand and update the README. Do not change the output of `list` or `show`.
