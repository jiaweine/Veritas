# Code Agent and operating-system tool integration

Veritas **already has a coding-agent connector**: `AcpTurnRunner` starts a
server-selected [Agent Client Protocol](https://agentclientprotocol.com/)
agent over stdio, supplies a per-run staged workspace, streams tool updates,
handles cancel and explicit permission decisions, and persists its work in
the existing Runs and Workspace Inspector. No second agent framework is needed.

## Where OS operations happen

The deterministic **Audit Agent** can read, inspect, locate and verify paper
evidence. It intentionally cannot run shell commands. The separate
**Replication Workspace** can ask an administrator-installed ACP coding agent
to run scripts, install tools, read/change code, and inspect project files.
Those operations are performed by the **configured coding-agent process**,
not by a new `/api/exec` endpoint or arbitrary commands supplied by the
browser.

The **default process runtime** is backward compatible but **not sandboxed**:
`cwd` is only the per-run workspace; an agent with terminal access may still
access host files and other OS resources under the service account.
Don't use this runtime for untrusted papers/code.

## Opt-in constrained Docker runtime

Prepare an image that contains your preferred ACP-capable code agent and its
dependencies. Use an immutable digest:

```bash
export VERITAS_REPLICATION_AGENT='coding-agent --acp'
export VERITAS_REPLICATION_CONTAINER_IMAGE='registry.example/agents/coding-agent@sha256:<64-hex-digest>'
export VERITAS_REPLICATION_CONTAINER_NETWORK=none
export VERITAS_REPLICATION_PERMISSION_POLICY=interactive
```

`VERITAS_REPLICATION_CONTAINER_IMAGE` opts into the existing ACP runner's
Docker launch path. Replace the image placeholder with a real SHA-256 digest.
Pull the image before running Veritas; its policy uses `--pull never`. Docker
must be installed on the server, not the browser or mobile device. This
does **not** provide a Docker installation or an ACP coding agent by itself.

The generated container command uses:
- **only** the current run workspace bind-mounted at `/workspace` as
  read-write; no home directory, Docker socket, or host root mount
- a read-only image filesystem and bounded writable `/tmp`
- non-root host UID/GID, all Linux capabilities dropped and
  `no-new-privileges`
- 128 process, 1 GiB memory, and 1 CPU limits
- `--network none` by default, with administrator-only opt-in `bridge`
- configured model credentials by **environment variable names**, never as
  literal command-line values; only explicitly forwarded keys are propagated

**Important limits:** Docker is a containment layer, not a universal
guarantee against kernel vulnerabilities, compromised Docker daemons,
malicious mounted files, or resource abuse. Binding the Docker daemon or
running privileged containers defeats the intended boundary. External
model APIs will **not be reachable** with network `none`; set
`VERITAS_REPLICATION_CONTAINER_NETWORK=bridge` only when those requests
are actually needed, and understand that generic bridge networking is
not an outbound domain allowlist. Network-enabled tools can send information
to external systems. Separate machine/VM isolation is preferable when
host data is sensitive.

## Permission behavior

The default `VERITAS_REPLICATION_PERMISSION_POLICY=deny` rejects tool
permission requests. `interactive` presents server-controlled **Allow once**
or **Reject** choices; it does not offer permanent approval. Server-side
`allow_once` auto-approves an offered allow-once option and should not be
enabled for untrusted workflows. The agent may have tools that do not request
ACP permission, so container controls are necessary independently of UI
approvals.

The control API does not currently provide a complete verified command
description after reconnection; the UI must **not** infer approval context
from request IDs alone. Reconnect/resume, stronger per-file policies, process
termination timeouts, and host-OS automation are separate follow-on work.

## Reusing existing source

- `src/veritas/replication/acp.py`: agent subprocess, permission broker,
  event limits, and optional Docker launch specification
- `src/veritas/harness/replication_guard.py`: artifact verification and run
  lifecycle preflight
- `src/veritas/harness/service.py`: run workspace creation, persisted events
- `src/veritas/harness/replication_workspace*.py`: bounded file/diff inspector
- `src/veritas/harness/web_core.py`: stream, control, cancellation, inspection
- `src/veritas/harness/static/reproduction.js`: Web client
- `mobile/ReplicationScreen.tsx`: mobile client

See `tests/test_replication_agent_container.py` for launch policy tests.
The tests do not launch Docker and **do not certify system isolation**.

## External building blocks worth evaluating

- [ACP specification](https://agentclientprotocol.com/protocol/overview)
  for interoperable terminal, file and permission methods
- [OpenHands sandbox architecture](https://docs.openhands.dev/)
  for dedicated agent runtimes and lifecycle patterns

Reuse the protocols and integrate existing implementations through ACP.
Do not copy an entire agent framework into Veritas, or silently grant a
research-review website direct host OS access.
