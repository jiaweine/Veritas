from veritas.runtime import numerical_backend_sha256, numerical_backend_versions


def test_numerical_backend_fingerprint_is_stable_and_complete():
    versions = numerical_backend_versions()
    assert set(versions) == {"python", "numpy", "scipy", "cvxpy", "scs"}
    assert all(versions.values())

    first = numerical_backend_sha256()
    second = numerical_backend_sha256()
    assert first == second
    assert len(first) == 64
