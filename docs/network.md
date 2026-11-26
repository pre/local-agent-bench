# Network

`agent_network = "proxy"` (the default) is the most isolated mode. The agent container has no network (`--network=none`). The harness listens on a Unix socket and sends each connection to the server URL. In the container, socat listens on `127.0.0.1:8080` and sends each connection to that socket. Thus Claude Code reaches only the server: no internet, no DNS, no other host service.

The relay works for an external and for a managed server. Another value of `agent_network` goes to `podman run --network`, and `agent_url` is then the server URL in the container. These modes are less isolated. Examples:

- `container:llama-qwen38` with `agent_url = "http://127.0.0.1:8080"`: the agent uses the network namespace of the server container. The agent can also reach the internet through it.
- `slirp4netns:allow_host_loopback=true` with `agent_url = "http://10.0.2.2:8080"`: the agent can reach the internet and all services on the loopback interface of the host.

The check container always has no network.

[ADR 0002](adr/0002-agent-without-network-behind-a-relay.md) gives the reason for the relay and the network modes that it replaced.
