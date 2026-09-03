# Sealed reproduction target secret v1

Private reproduction targets are orchestrator-only inputs. They must never be mounted into a CodeAgent workspace or persisted in an answer-free comparison certificate.

## Single-target form

A single target is either the legacy unversioned v1 object or the same object with `"schema_version": 1`.

Required keys are `target_id`, `claim_id`, `metric`, and `reported`. Optional keys are `source` and `materiality`. No undeclared keys are accepted.

`reported` contains exactly `value` plus optional `decimals` and `operator`. `value` must be a finite JSON number, `decimals` must be a non-negative integer when present, and `operator` must be one of the supported comparison operators.

`source` accepts only the fields represented by `SourceLocation`; typed page/character offsets and a four-number bounding box are validated before the target commitment is reconstructed.

## Target-set form

The root contains exactly `schema_version` and `targets`, with `schema_version` equal to integer `1`. Every target row uses the same exact target schema as the single-target form, except row-level schema versions are forbidden.

Target order is security-significant because the ordered target set is bound by `target_commitment_sha256`.

## Fail-closed rules

Duplicate JSON keys, non-standard JSON numeric constants, non-finite reported values, booleans used as integers or numbers, numeric strings, unsupported materiality values, unknown source fields, and unknown target fields are rejected before comparison.
