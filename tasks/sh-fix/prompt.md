`bin/rotate-logs.sh` gave us two bad surprises this week on the log hosts (cron entries are in `deploy/rotate-logs.cron`).

1. The payment gateway logs are never archived. Its log directory is `/srv/logs/payment gateway`, and `/var/log/rotate-logs.log` shows lines like `find: '/srv/logs/payment': No such file or directory` for that entry. In billing, the file `export errors.log` is also never rotated and keeps growing, while the other billing logs rotate fine.

2. On Tuesday `/srv/archive` was full. The billing job still logged `done, 6 file(s) rotated` and cron saw exit status 0, but the new archives were empty or cut off, and the logs had been truncated anyway. We lost a day of billing logs.

Please fix the script. What we need:
- Log and archive directories and log file names with spaces must work for all steps, including the removal of old archives (`KEEP`).
- If a log cannot be archived completely, the script must leave that log untouched and exit with a non-zero status. It can still process the other logs.
- Keep the usage, the archive and checksum file names and the `KEEP` and `STAMP` variables as they are.
- CI runs `shellcheck bin/*.sh` with the default settings, and it must report nothing for this script.
