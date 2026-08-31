# PDF ingestion and hard-audit promotion contract

Method snapshot date: 2026-08-31.

Veritas treats document parsing as an uncertain measurement process. A parser, VLM, or LLM never directly creates a detector-ready statistical object.

## Two separate evaluation layers

### Document parsing
Evaluate the fidelity of PDF structure recovery separately for:

- text;
- tables;
- formulas;
- reading order;
- page/block/span localization.

OmniDocBench is an anchor because it evaluates these components independently and preserves localization annotations. TableEval is an anchor because scientific tables are empirically harder for LLMs than many non-scientific tables.

### Statistical-object extraction
A separate benchmark must score:

- statistical object type;
- exact/rounding-compatible numerical fields;
- table row/column identity;
- sample/model identity;
- critical semantic applicability gates;
- source page/table/section/span identity;
- calibrated abstention and conflict behavior.

A high document-parsing score does not certify semantic applicability.

## Evidence ledger

Every candidate field and semantic gate is stored with:

- raw text;
- normalized value;
- parser id and parser family;
- nonconformity score;
- precise `SourceLocation`;
- conformal resolution;
- extraction confidence;
- evidence note.

The ledger also locks:

- source artifact SHA-256;
- calibration SHA-256;
- parser versions;
- object-schema version;
- promotion-policy version.

The resulting hashes are attached to any finding produced through `AuditEngine.audit_verified()`.

## Hard-audit promotion

Promotion to `DetectorInputEnvelope` requires all of the following for every required field and critical semantic gate:

1. the source artifact has a content SHA-256;
2. the calibrated extraction resolution is `ACCEPT`;
3. enough independent parser families support the accepted value;
4. the extraction confidence meets the promotion policy;
5. every accepted candidate carries the required page and location anchor;
6. all required numerical fields are present;
7. all critical semantic gates are present.

Failure modes are intentionally asymmetric:

- parser conflict -> `REVIEW`;
- accepted but below confidence policy -> `REVIEW`;
- missing field/gate, missing artifact hash, domain shift, or inadequate provenance -> `UNVERIFIABLE`;
- only fully promoted objects may enter the verified hard-audit path.

## Numeric evidence vs semantic evidence

Numerical claims and methodological applicability are separate evidence types.

Example:

- `t = 2.31` may be extracted from a results table;
- `test_definition = welch` must be supported by methods text or another explicit methodological source.

Agreement about the number does not prove agreement about the estimator or inference procedure.

## Reproducibility

`IngestionProtocol`, `PromotionSpec`, and the evidence payload each have stable SHA-256 identities. Re-running a finding therefore records which PDF bytes, calibration set, parser versions, extraction evidence, and promotion policy produced the detector input.

## Method anchors

- OmniDocBench, CVPR 2025: https://github.com/opendatalab/OmniDocBench
- Borisova et al. (2025), Table Understanding and (Multimodal) LLMs: A Cross-Domain Case Study, DOI 10.18653/v1/2025.trl-1.10
- Wang et al. (2025), SConU: Selective Conformal Uncertainty in Large Language Models, ACL 2025
- Towards Statistical Factuality Guarantee for Large Vision-Language Models, EMNLP 2025
