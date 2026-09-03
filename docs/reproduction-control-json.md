# Strict reproduction control JSON

Veritas treats reproduction packets, execution attestations, private targets, and JSON-bound output artifacts as security-sensitive control inputs.

All JSON consumed by the sealed reproduction ingest path is decoded with one strict policy:

- UTF-8 only;
- duplicate object keys are rejected;
- non-standard numeric constants (`NaN`, `Infinity`, and `-Infinity`) are rejected;
- numeric values that are later interpreted as reproduction results or sealed reported values must be finite;
- booleans are not accepted as numeric values.

The same decoder is used for both single-target and target-set file ingest so that a sealed artifact cannot acquire different meaning depending on which reproduction entrypoint reads it.

This parsing policy does not add production authority or E4 evidence authority. It only makes the descriptive ingest boundary deterministic and fail-closed.
