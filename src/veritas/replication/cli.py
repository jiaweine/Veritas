from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .acp import AcpTurnRunner, AgentCommand, PermissionPolicy, agent_from_environment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Veritas replication turn through an ACP agent.")
    parser.add_argument("prompt", help="Instruction to send to the replication agent")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Replication workspace directory")
    parser.add_argument(
        "--agent",
        help="ACP agent command. Defaults to VERITAS_REPLICATION_AGENT.",
    )
    parser.add_argument(
        "--forward-env",
        action="append",
        default=[],
        metavar="NAME",
        help="Explicitly forward one environment variable to the agent process. Repeatable.",
    )
    parser.add_argument(
        "--allow-once",
        action="store_true",
        help="Select only ACP allow_once permission options. Default is deny all permission requests.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    if args.agent:
        agent = AgentCommand.from_shell(
            args.agent,
            name="ACP agent",
            forward_env=tuple(args.forward_env),
        )
    else:
        agent = agent_from_environment()
        if agent is None:
            raise SystemExit(
                "No ACP agent configured. Pass --agent or set VERITAS_REPLICATION_AGENT."
            )
        if args.forward_env:
            agent = AgentCommand(
                argv=agent.argv,
                name=agent.name,
                forward_env=tuple(dict.fromkeys((*agent.forward_env, *args.forward_env))),
                env=agent.env,
            )

    policy = PermissionPolicy.ALLOW_ONCE if args.allow_once else PermissionPolicy.DENY
    runner = AcpTurnRunner(agent, permission_policy=policy)
    async for event in runner.stream_turn(args.workspace, args.prompt):
        print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
