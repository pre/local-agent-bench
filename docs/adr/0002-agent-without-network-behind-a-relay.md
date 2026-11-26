# The agent container has no network and reaches the server through a relay

Status: accepted.

The agent runs with `--dangerously-skip-permissions`, and it must reach only the inference server: no internet, no DNS, no other service of the host. Thus the agent container has no network (`--network=none`), and a relay of the harness on a Unix socket is its only path to the server. Each podman network mode that was examined gave the agent a path to the internet or to external DNS.

## Decision

- The harness listens on a Unix socket in a directory that the agent container mounts. In the container, socat listens on `127.0.0.1:8080` and sends each connection to that socket.
- For a local server (external or managed), the relay sends each connection to the server URL.
- For a remote endpoint, the relay is an HTTP proxy that accepts only `CONNECT` to the host and port of the endpoint. TLS goes from Claude Code to the endpoint, and the harness does not see the request.
- `agent_network = "proxy"` selects the relay and is the default. Another value goes to `podman run --network` and is less isolated.
- The diff container and the check container have no network and no relay.

## Considered Options

- An internal podman network (`podman network create --internal`) for the server container and the agent container, the first plan: the internal network resolves external DNS names.
- `--network container:<server container>`: the agent got internet access through slirp4netns.
- `slirp4netns:allow_host_loopback=true` for an external server: the agent can reach the internet and all services on the loopback interface of the host.

## Consequences

- The agent image must have socat, and the agent command starts behind a script that waits until socat listens.
- A task must work with no network: standard library only, or vendored dependencies.
- The path to the server is the same for the three server modes.
- Each request of the agent to another host fails, also the telemetry of Claude Code. For a remote endpoint the proxy answers HTTP 403.
- The relay isolates only the network. With a remote endpoint the agent can read the secret values in its environment and can use them with the endpoint.
