# PDF ingestion, detector promotion, and production authority

Method snapshot date: 2026-08-31.

Veritas treats document parsing as an uncertain measurement process. A parser, VLM, or LLM never directly creates a production-authorized statistical finding.

## Three separate evaluation layers

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

### Production authority
A detector may be exercised for benchmark or research purposes without being allowed to issue a production hard finding. Calibration authority is therefore carried explicitly by `CalibrationScope`:

- `UNVERIFIED`: no calibration authority claim;
- `BENCHMARK`: evaluation-only calibration;
- `RESEARCH`: research use without production authority;
- `PRODUCTION_CERTIFIED`: eligible for production authority only when accompanied by a matching held-out certificate.

The calibration scope and production-certificate identity are included in the `IngestionProtocol` SHA-256. Relabeling a benchmark calibration or swapping a certificate therefore changes the protocol identity and cannot be invisible in provenance.

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
- calibration scope;
- production-certificate SHA-256 when present;
- parser versions;
- object-schema version;
- promotion-policy version.

## Detector promotion

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
- missing field/gate, missing artifact hash, domain shift, inadequate provenance, or a production certificate that does not cover the current promotion spec -> `UNVERIFIABLE`;
- only `PROMOTE` objects receive a detector envelope.

`PromotionReport.detector_ready` means the extraction/promotion contract was satisfied. It does **not** mean the calibration is production-certified.

## Held-out production certification

`ProductionCalibrationCertificate` is a deterministic, hash-bound provenance artifact. It is **not** a cryptographic signature, institutional endorsement, or external trust service.

A production certificate may be issued only when:

1. every certification case belongs to the locked `TEST` split;
2. exactly one paper-level outcome is supplied for every paper in that TEST manifest;
3. paper-level expected-material-issue labels agree with the benchmark cases;
4. the paper-level certification policy passes.

The default strict policy requires, among other conditions:

- at least 300 applicable clean papers;
- at least 50 applicable positive papers;
- a 95% one-sided exact Clopper-Pearson upper bound on the paper-level false hard-alert rate of at most 1%;
- a 95% one-sided exact lower bound on hard-alert precision of at least 95%.

Multiple findings from one paper count once for certification. This prevents correlated consequences of one underlying error from artificially inflating evidence.

Certificate v2 binds all of the following:

- calibration SHA-256;
- exact parser ids and versions;
- object-schema version;
- promotion-spec SHA-256;
- TEST benchmark-manifest SHA-256;
- audited Veritas-system SHA-256;
- certification-policy SHA-256;
- certification-report SHA-256;
- resulting paper-level uncertainty bounds and corpus counts.

`IngestionProtocol(PRODUCTION_CERTIFIED)` rejects a certificate whose calibration, parser versions, or object schema differ from the protocol. During promotion, a different `PromotionSpec` is rejected as `UNVERIFIABLE` and receives no detector envelope.

## Audited system identity

`AuditEngine.manifest_sha256()` binds three independent identities:

1. the SHA-256 of the installed `veritas/**/*.py` source tree;
2. the registered detector ids and declared detector versions;
3. the numerical backend identity, including Python, NumPy, SciPy, CVXPY, and SCS versions.

Hashing the source tree is deliberately stricter than relying on detector version strings alone. A detector implementation, parser helper, scoring helper, or other Veritas Python source change invalidates a previously certified system manifest even when a developer forgets to bump a detector version.

External PDF parser versions remain separately locked by the ingestion protocol and the production certificate.

## Hard-audit authority

`PromotionReport.hard_audit_ready` is true only when all of the following hold:

1. the object is detector-ready;
2. the scope is `PRODUCTION_CERTIFIED`;
3. a held-out certificate is attached;
4. the current promotion-spec SHA-256 equals the certificate's certified promotion-spec SHA-256;
5. a certified audited-system SHA-256 is present.

Veritas then adds a second explicit gate at audit execution:

- `AuditEngine.audit_verified()` is for research/benchmark verification and always records `production_hard_finding_authorized = false`;
- `AuditEngine.audit_production_verified()` rejects envelopes without certificate authority and rejects certificates issued for a different current Veritas/numerical system manifest.

Production findings preserve:

- source artifact SHA-256;
- ingestion-protocol SHA-256;
- promotion-spec SHA-256;
- extraction-evidence SHA-256;
- calibration scope;
- production-certificate SHA-256;
- certified promotion-spec SHA-256;
- certified system SHA-256;
- actually executed system SHA-256;
- whether production hard-finding authority was active.

This intentionally separates **detector arithmetic severity** from **publication/production authority**. A benchmark run can reveal an E3 mathematical contradiction for evaluation without that output being presented as an authorized production research-integrity finding.

## Current certification status

The current open-access real-PDF smoke and selective-promotion benchmarks are explicitly **not production certification**. They validate extraction, fail-closed behavior, and experimental detector promotion. Their `CalibrationScope` remains `BENCHMARK`, and production hard-authority coverage is expected to remain zero.

A real production certificate should not be issued until a sufficiently large locked TEST corpus meets the paper-level certification policy for the exact parser/schema/spec/system combination being deployed.

## Numeric evidence vs semantic evidence

Numerical claims and methodological applicability are separate evidence types.

Example:

- `t = 2.31` may be extracted from a results table;
- `test_definition = welch` must be supported by methods text or another explicit methodological source.

Agreement about the number does not prove agreement about the estimator or inference procedure.

## Reproducibility

`IngestionProtocol`, `PromotionSpec`, extraction evidence, production certificate, benchmark manifest, certification policy/report, Veritas source tree, detector registry, and numerical backend all have stable SHA-256 identities. Production authorization is therefore tied to the exact evaluated pipeline rather than to a mutable label.

## Method anchors

- OmniDocBench, CVPR 2025: https://github.com/opendatalab/OmniDocBench
- Borisova et al. (2025), Table Understanding and (Multimodal) LLMs: A Cross-Domain Case Study, DOI 10.18653/v1/2025.trl-1.10
- Wang et al. (2025), SConU: Selective Conformal Uncertainty in Large Language Models, ACL 2025
- Towards Statistical Factuality Guarantee for Large Vision-Language Models, EMNLP 2025
