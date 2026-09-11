from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path

import cvxpy
import numpy
import scipy
import scs


def numerical_backend_versions() -> dict[str, str]:
    """Return the numerical software identities that can affect audit results."""
    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "cvxpy": cvxpy.__version__,
        "scs": getattr(scs, "__version__", "unknown"),
    }


def numerical_backend_sha256() -> str:
    payload = numerical_backend_versions()
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def veritas_source_sha256() -> str:
    """Hash the installed Veritas Python source tree used by the running audit system.

    Production certification should fail closed when implementation code changes even if a detector
    author forgets to bump a declared detector version. The relative path and exact bytes of every
    ``*.py`` file under the installed ``veritas`` package are included in the digest.
    """
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()
