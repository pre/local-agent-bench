# addrplan

Computes the host name, BMC address, VLANs and MTUs of a cluster node from
its site, rack and slot, as the network and node addressing standard
(`docs/network-standard.md`) describes. The provisioning pipeline imports
`addrplan.plan`.

```
python -m addrplan nodes-example.csv
python -m unittest discover -s tests -t .
```
