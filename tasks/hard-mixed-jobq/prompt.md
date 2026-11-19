The version 2 contract of jobq is approved. It is in `docs/CONTRACT.md` (section "Version 2", rules 1 to 19). Please implement it in all parts of the repository: the Go server in `service/`, the Python client and its command line in `client/`, the deploy script and the env files in `deploy/`, and the Kubernetes templates in `deploy/templates/`.

- Version 2 replaces version 1 completely. Do not keep version 1 paths, fields or variables.
- The parts must agree with each other. For example, the server must start and become ready with exactly the environment, the files and the ports that the rendered Deployment gives it, and the client must work against the real server.
- Update the tests in `service/` and `client/` for version 2. `go test ./...` in `service/`, `python3 -m unittest discover` in `client/` and `shellcheck deploy/deploy.sh` must pass.
- Use the standard libraries only (Go and Python). There is no network access.
- Update the README if a command in it changes.
