from veritas.methodology import get_method_anchor, methodology_snapshot_sha256


def test_methodology_registry_is_versionable():
    anchor = get_method_anchor("weak_iv_jep_2026")

    assert anchor.year == 2026
    assert anchor.status == "published"
    assert len(methodology_snapshot_sha256()) == 64
