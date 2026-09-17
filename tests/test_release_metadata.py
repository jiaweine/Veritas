from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import veritas
from veritas.harness import benchmark_cli
from veritas.harness import cli as harness_cli
from veritas.harness import workspace_cli
from veritas.harness.web import create_app
from veritas.replication import cli as replication_cli
from veritas.version import package_version


def test_public_version_matches_installed_distribution() -> None:
    assert veritas.__version__ == package_version()


def test_health_routes_and_capabilities_share_package_version(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    expected_version = package_version()

    legacy = client.get("/api/health")
    versioned = client.get("/api/v1/health")

    assert legacy.status_code == 200
    assert versioned.status_code == 200
    assert legacy.json() == versioned.json()
    assert versioned.json() == {
        "status": "ok",
        "service": "veritas-harness",
        "api_version": "v1",
        "version": expected_version,
    }

    capabilities = client.get("/api/v1/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["version"] == expected_version
    assert capabilities.json()["api_version"] == "v1"
    assert client.app.version == expected_version


@pytest.mark.parametrize(
    "build_parser",
    [
        harness_cli.build_parser,
        replication_cli.build_parser,
        benchmark_cli.build_parser,
        workspace_cli.build_parser,
    ],
)
def test_cli_version_exits_without_running_product(build_parser, capsys) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    assert exc_info.value.code == 0
    assert package_version() in capsys.readouterr().out
