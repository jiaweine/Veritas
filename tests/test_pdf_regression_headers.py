from veritas.pdf_regression import _header_role, _normalized_header


def test_greek_beta_header_normalizes_to_beta() -> None:
    assert _normalized_header("β") == "beta"
    assert _normalized_header("Β") == "beta"
    assert _header_role("β") == "beta"


def test_indexed_beta_header_maps_to_coefficient_role() -> None:
    assert _normalized_header("β i") == "betai"
    assert _normalized_header("β_i") == "betai"
    assert _header_role("β i") == "beta"
    assert _header_role("β_i") == "beta"
    assert _header_role("β0") == "beta"
    assert _header_role("β12") == "beta"
    assert _header_role("beta estimate adjusted") is None


def test_independent_variable_header_maps_to_variable_role() -> None:
    assert _normalized_header("Independent variable") == "independentvariable"
    assert _header_role("Independent variable") == "variable"
