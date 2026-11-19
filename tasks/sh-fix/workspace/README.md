# logtools

Small tools for the log hosts of the platform team.

| Tool | What it does |
|---|---|
| `bin/rotate-logs.sh LOG_DIR ARCHIVE_DIR` | Compresses each `*.log` in `LOG_DIR` to `ARCHIVE_DIR`, writes a SHA-256 file next to each archive, truncates the log and keeps the `KEEP` newest archives of each log |

`deploy/rotate-logs.cron` is the cron file of the log hosts. Configuration
management installs the tools to `/opt/logtools`.

## Tests

```
tests/smoke.sh
```

CI runs `shellcheck bin/*.sh` and `tests/smoke.sh`.
