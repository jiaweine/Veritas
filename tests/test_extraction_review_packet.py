import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_review_packet import build_blinded_seed_review_packets

SEED_PATH = Path(__file__).resolve().parents[1] / "benchmark" / "extraction" / "seed_cases_v0.11.json"


def _seed():
    raw = SEED_PATH.read_bytes()
    return json.loads(raw), sha256(raw).hexdigest()


def test_seed_review_packets_are_double_blinded_and_exclude_legacy_values():
    seed, seed_sha = _seed()
    packets = build_blinded_seed_review_packets(seed, seed_manifest_sha256=seed_sha)
    assert len(packets) == 2
    assert packets[0].reviewer_slot != packets[1].reviewer_slot
    assert packets[0].targets == packets[1].targets
    assert packets[0].blinded_to_legacy_values is True
    assert packets[0].blinded_to_other_reviews is True

    legacy_values = {
        str(value)
        for case in seed["cases"]
        for value in case["expected_fields"].values()
    }
    rendered = json.dumps(packets[0].to_payload(), ensure_ascii=False, sort_keys=True)
    for value in legacy_values:
        assert value not in rendered


def test_seed_review_packet_creates_one_target_per_requested_field():
    seed, seed_sha = _seed()
    packets = build_blinded_seed_review_packets(seed, seed_manifest_sha256=seed_sha)
    expected_target_count = sum(len(case["expected_fields"]) for case in seed["cases"])
    assert len(packets[0].targets) == expected_target_count
    assert len(packets[0].targets) >= 20
    assert all(target.target_id.endswith((":beta", ":se", ":t_stat", ":p_value")) for target in packets[0].targets)


def test_review_packet_rejects_seed_that_already_has_a_split():
    seed, seed_sha = _seed()
    seed["cases"][0]["split"] = "test"
    try:
        build_blinded_seed_review_packets(seed, seed_manifest_sha256=seed_sha)
    except ValueError as exc:
        assert "unsplit" in str(exc)
    else:
        raise AssertionError("review packets must be generated before split assignment")
