from veritas.pdf_regression import _header_role, _normalized_header


def test_greek_beta_header_normalizes_to_beta() -> None:
    assert _normalized_header("β") == "beta"
    assert _normalized_header("Β") == "beta"
    assert _header_role("β") == "beta"


def test_independent_variable_header_maps_to_variable_role() -> None:
    assert _normalized_header("Independent variable") == "independentvariable"
    assert _header_role("Independent variable") == "variable"
