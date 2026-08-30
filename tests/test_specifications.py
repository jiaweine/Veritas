from veritas.specifications import (
    Specification,
    SpecificationConstraint,
    SpecificationEstimate,
    SpecificationSpace,
    summarize_specification_robustness,
)


def test_specification_space_excludes_inadmissible_combinations():
    space = SpecificationSpace(
        dimensions={
            "controls": ("baseline", "extended"),
            "fe": ("unit_time", "unit_only"),
        },
        constraints=(
            SpecificationConstraint(
                "controls",
                "extended",
                "fe",
                "unit_only",
                rationale="pre-specified design rule",
            ),
        ),
    )

    specs = space.enumerate()

    assert len(specs) == 3
    assert len(space.stable_sha256()) == 64


def test_equivalence_groups_prevent_duplicate_specs_from_dominating():
    base = Specification("s1", (("controls", "base"),), "family-a")
    duplicate = Specification("s2", (("controls", "base"),), "family-a")
    alternative = Specification("s3", (("controls", "alt"),), "family-b")
    estimates = [
        SpecificationEstimate(base, 1.0, original=True),
        SpecificationEstimate(duplicate, 1.0),
        SpecificationEstimate(alternative, -1.0),
    ]

    summary = summarize_specification_robustness(estimates)

    assert summary.n_equivalence_groups == 2
    assert summary.weighted_mean == 0.0
    assert summary.sign_stability == 0.5


def test_summary_tracks_practical_stability_and_original_position():
    specs = [Specification(f"s{i}", (("controls", str(i)),), f"g{i}") for i in range(4)]
    estimates = [
        SpecificationEstimate(specs[0], 0.20, original=True),
        SpecificationEstimate(specs[1], 0.18),
        SpecificationEstimate(specs[2], 0.05),
        SpecificationEstimate(specs[3], -0.02),
    ]

    summary = summarize_specification_robustness(estimates, practical_threshold=0.10)

    assert summary.sign_stability == 0.75
    assert summary.practical_effect_stability == 0.5
    assert summary.original_percentile == 1.0
    assert "controls" in summary.dimension_influence
