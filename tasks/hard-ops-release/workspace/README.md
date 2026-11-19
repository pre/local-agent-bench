# relctl

`relctl` installs release packages of a service on one host, keeps older releases for a rollback, and removes old releases.

## Files

| Path | Content |
|---|---|
| `bin/relctl` | the installer |
| `docs/REQUIREMENTS.md` | the specification (R1 to R26) |
| `etc/relctl.conf.example` | an example configuration |
| `tools/make-package.sh` | makes a package and its checksum file from a directory |
| `tests/smoke.sh` | a smoke test: two installs in a scratch directory |

## Use

```sh
tools/make-package.sh build/ inventory-api-1.4.0.tar.gz
bin/relctl --config /etc/relctl/relctl.conf install inventory-api-1.4.0.tar.gz
bin/relctl status
bin/relctl rollback
```

## Development

```sh
tests/smoke.sh
shellcheck bin/relctl tools/*.sh tests/*.sh
```
