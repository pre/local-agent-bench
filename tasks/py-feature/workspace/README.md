# nodeinv

Query the node inventory of a Kubernetes cluster. The inventory is a TOML file
that the platform team keeps next to the cluster configuration.

Python 3.11 or later. No dependencies outside the standard library.

## Usage

```
python -m nodeinv [--inventory FILE] list [--role ROLE] [--zone ZONE] [--label KEY=VALUE]... [--include-cordoned] [--json]
python -m nodeinv [--inventory FILE] show NAME
```

The default inventory file is `$NODEINV_INVENTORY`, or `inventory.toml` in the
current directory.

`list` does not show cordoned nodes unless you give `--include-cordoned`.
Each `--label` adds one condition; a node must match all of them.

Example:

```
$ python -m nodeinv list --role control-plane
NAME            ROLE           ZONE    RACK  CPU  MEMORY  GPU  STATUS
hel1-cp-r01-01  control-plane  hel1-a  r01    32  128Gi     0  ready
hel1-cp-r02-01  control-plane  hel1-b  r02    32  128Gi     0  ready
hel1-cp-r03-01  control-plane  hel1-c  r03    32  128Gi     0  ready
```

## Inventory format

```toml
[cluster]
name = "hel1-prod-02"

[[nodes]]
name = "hel1-gpu-r07-01"
role = "gpu-worker"
zone = "hel1-a"
rack = "r07"              # optional
cpu = 192
memory = "2Ti"            # Mi, Gi or Ti
gpu = { model = "MI300X", count = 8 }   # optional
cordoned = false          # optional
labels = { pool = "gpu" } # optional
```

## Tests

```
python -m unittest discover -s tests -t .
```
