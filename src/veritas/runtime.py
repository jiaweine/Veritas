from __future__ import annotations

import hashlib
import json
import platform

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
