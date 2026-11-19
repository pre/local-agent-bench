# jobq

A small job queue service. The contract between the parts is in
`docs/CONTRACT.md`.

| Directory | Content |
|---|---|
| `service/` | The server `jobq-server` (Go, standard library only) |
| `client/` | The Python client `jobq_client` and its command line (standard library only) |
| `deploy/` | `deploy.sh`, the values of each environment (`env/`) and the Kubernetes templates (`templates/`) |

## Build and test

```sh
(cd service && go build -o jobq-server ./cmd/jobq-server && go test ./...)
(cd client && python3 -m unittest discover -v)
shellcheck deploy/deploy.sh
deploy/deploy.sh --env staging --render-only rendered/staging
```

CI runs these commands. The CD job runs `deploy/deploy.sh` without
`--render-only`. The image entrypoint is the server binary.
