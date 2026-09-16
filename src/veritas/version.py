from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION_NAME = "veritas-audit"


def package_version() -> str:
    """Return the installed Veritas distribution version.

    Source-only checkouts that have not been installed deliberately report an
    unknown development version instead of duplicating the version declared in
    pyproject.toml.
    """

    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "0+unknown"
