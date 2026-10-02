# Claim-graph design descriptor schema

`veritas.claim_design_reconstruction.reconstruct_design_descriptor()` reconstructs paper-only DiD, IV, and RDD detector inputs from a serialized `StatisticalClaimGraph` object without parser state.

A generic node uses `object_type="DesignDescriptor"` and an explicit string field `design_family` (`did`, `iv`, or `rdd`). Dedicated `DIDDesign`, `IVDesign`, and `RDDDesign` object types are also accepted. Every field remains an `ExtractedField`, so raw display text, source location, extraction confidence, displayed precision/operator, and identity confidence survive graph JSON round-trip.

## DiD

Supported scalar fields include `periods`, `staggered_adoption`, `treatment_type`, `estimator`, `event_study`, `heterogeneity_robust_estimator_reported`, `treatment_timing`, `comparison_group`, `event_time_start`, `event_time_end`, `pretrend_test`, and `parallel_trends_claimed`. Repeated fixed effects and clustering dimensions use zero-based contiguous keys `fixed_effect:<index>` and `clustering:<index>`.

If `treatment_type` is absent, reconstruction uses the conservative value `unknown` rather than inheriting the `DIDDesign` model's convenience default of `binary`. Event-time bounds must either both be present or both be absent.

## IV

Supported fields include `single_instrument`, `single_endogenous_regressor`, `just_identified`, `instrument_count`, `endogenous_regressor_count`, `first_stage_reported`, `reduced_form_reported`, `two_stage_least_squares_reported`, `first_stage_f`, and `uses_f_gt_10_rule_as_validity_claim`. Weak-robust methods use zero-based contiguous `weak_robust_method:<index>` fields.

`weak_robust_methods_complete=true` is mandatory before reconstruction. This prevents an omitted extraction inventory from being silently interpreted as evidence that no Anderson-Rubin/tF-style method was reported. `uses_f_gt_10_rule_as_validity_claim` is also required explicitly. `first_stage_f` is a reported numeric field and therefore requires an explicit comparison operator and retains displayed precision.

## RDD

`framework` and `design_type` are mandatory. Supported fields include `estimator`, `running_variable`, `cutoff`, `bandwidth`, `bandwidth_selection`, `kernel`, `inference_description`, `global_polynomial_order`, `robust_bias_corrected_inference`, `alternative_modern_inference_reported`, `randomization_inference_reported`, `continuity_check_claimed`, `continuity_check_reported`, `manipulation_check_claimed`, and `density_test_reported`.

`cutoff` and `bandwidth` are reported numeric fields and require explicit display comparison operators. Unknown frameworks/types are represented explicitly rather than inferred from nearby method names.

## Evidence boundary

Reconstruction only rebuilds typed detector inputs. It does not upgrade extraction/model output into E3+ evidence. Design detectors preserve their paper-only `DESIGN_VALIDITY` / `METHODOLOGICAL_RISK` boundary, and incomplete detector-relevant semantics fail closed rather than being guessed.
