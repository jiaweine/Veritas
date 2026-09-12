# Replication agent backends

Veritas separates paper auditing from code execution.

```text
Research Audit Harness → evidence tools → read / locate / verify
Replication Workspace  → ACP adapter    → execute / propose / review
```

The replication layer uses the **Agent Client Protocol (ACP)** as its adapter boundary. Veritas does not vendor a coding-agent runtime or copy another project's UI. An ACP-compatible agent runs as a child process and sends structured session updates back to Veritas.

This keeps the research product stable while allowing the coding backend to evolve independently.

## Why ACP

ACP gives Veritas a common session, streaming-update, and permission protocol for code-capable agents. The Python adapter uses the official `agent-client-protocol` SDK and communicates with agents over stdio.

The first recommended backend is **Codex through `codex-acp`**. Other ACP-compatible agents can use the same adapter without changing Veritas's audit engine or evidence model.

| Backend | Role in Veritas | Integration choice |
| --- | --- | --- |
| Codex via `codex-acp` | Recommended first replication agent | ACP child process |
| OpenHands | Strong option for managed or ephemeral workspaces | Add an ACP bridge or separate Agent Server adapter |
| Cline | Optional developer-agent backend | Prefer ACP/CLI bridge instead of embedding its UI |
| mini-SWE-agent | Minimal agent/ACI reference | Useful for experiments and design comparison |

## Install the adapter

```bash
python -m pip install -e ".[replication]"
```

Configure any ACP-compatible executable:

```bash
export VERITAS_REPLICATION_AGENT="my-acp-agent"
export VERITAS_REPLICATION_AGENT_NAME="My Agent"
veritas-replication --workspace ./reproduction \
  "Run the project tests and identify the command that reproduces Table 4."
```

The command prints NDJSON events so the same stream can later be rendered by the browser Replication Workspace.

## Codex backend

Install an ACP bridge for Codex separately from Veritas, then point the adapter at it. A typical local setup is:

```bash
npm install -g @agentclientprotocol/codex-acp
export VERITAS_REPLICATION_AGENT="codex-acp"
export VERITAS_REPLICATION_AGENT_NAME="Codex"
```

Authentication remains owned by the selected backend. Veritas does not automatically pass arbitrary environment variables to agent processes. If a backend requires an environment credential, forward it explicitly:

```bash
export VERITAS_REPLICATION_FORWARD_ENV="OPENAI_API_KEY"
```

Multiple names are comma-separated.

## Permission policy

The host-side default is **deny**. If an ACP agent asks the client for a tool permission, Veritas returns a cancelled outcome unless the operator explicitly starts the turn with `--allow-once`.

```bash
veritas-replication --allow-once --workspace ./reproduction \
  "Run the smallest test command needed to reproduce the reported result."
```

`--allow-once` may select only an ACP option whose kind is exactly `allow_once`. It never converts a request into `allow_always`.

This policy is deliberately narrower than a general autonomous coding environment.

## Environment boundary

The adapter starts the agent with a small process environment. It forwards basic process variables such as `PATH`, `HOME`, locale, and temporary-directory settings. Other variables are omitted unless named explicitly with `--forward-env` or `VERITAS_REPLICATION_FORWARD_ENV`.

This reduces accidental credential exposure, but it is not a sandbox.

## Sandbox boundary

A workspace path is a **working directory, not a security boundary**. ACP standardizes communication and permission requests; it does not by itself contain every file, network, or process action an agent runtime may perform.

Isolation must therefore be provided by the selected replication backend or its container/VM runtime. For research reproduction, prefer a disposable workspace with explicit filesystem and network policy. Do not treat a local `cwd` restriction as equivalent to sandboxing.

## Evidence boundary

A coding agent can inspect, execute, diagnose, and propose changes. Its output is not automatically a Veritas finding.

Replication results should be converted into normal Veritas artifacts before they are used as audit evidence: command identity, environment, inputs, outputs, publication-object match, source locations, and provenance. The deterministic audit/evidence layer remains authoritative for Veritas findings.

## Browser integration

The ACP adapter is the backend foundation for a future browser **Replication Workspace**. The Research Audit Harness remains paper-first. The replication surface can later render the same structured events with terminal output, diffs, approvals, generated artifacts, and publication matches without giving ordinary audit threads code-execution privileges.
