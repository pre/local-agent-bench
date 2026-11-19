`bin/relctl` is our release installer. The first version works for the happy path on a test host, but it is not safe for production: it runs the configuration file as shell code, breaks on paths with spaces, has no lock, leaves a half-installed release when the health check fails or when somebody pushes Ctrl-C, and has no rollback.

The operations team wrote down what the installer must do in `docs/REQUIREMENTS.md` (rules R1 to R26). Please make `bin/relctl` meet all of these rules. You can rewrite the script completely.

- All rules apply together, for all commands: read the complete document before you start, and check your result against each rule at the end.
- Keep `bin/relctl` one bash script. `tools/make-package.sh` makes test packages. Update `tests/smoke.sh` when necessary, and add more tests if they help you.
- Do not change `docs/REQUIREMENTS.md`.
