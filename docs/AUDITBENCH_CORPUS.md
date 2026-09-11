# AuditBench Real-Corpus Protocol

AuditBench must evaluate Veritas on real reporting styles without turning publication venue, openness, or reputation into a proxy for research integrity.

## Unit of ground truth

The gold unit is a **claim-detector pair**, not a paper-level label.

A corpus label states only whether a specific detector is applicable to a specific statistical object and, when applicable, whether the modeled relation is consistent with the available evidence.

AuditBench does **not** assign `clean paper`, `fraud paper`, or author-level labels.

## Three evidence bases

1. `controlled_corruption`
   - starts from a manually verified negative-control claim;
   - changes exactly one locked quantity or analysis choice;
   - stores an immutable corruption manifest hash;
   - preserves the original artifact separately.

2. `manual_reconstruction`
   - two independent reviewers reconstruct the relevant relation from the paper/appendix;
   - disagreements are adjudicated before a natural consistent/inconsistent label enters the benchmark.

3. `documented_reproduction`
   - uses a public, citable reproduction record or reproducibility report;
   - the benchmark label still refers to a claim-level fact, not a paper-level reputation judgment.

Natural `consistent` and `inconsistent` labels require two independent reviewers plus adjudication. `unverifiable` and `not_relevant` labels may be used to evaluate abstention and applicability behavior.

## Article-family leakage control

All versions of one research article share one `article_family_id`:

- working paper;
- preprint;
- accepted manuscript;
- journal version;
- correction/erratum;
- repository mirror containing materially the same reported claims.

Train/development/test assignment is performed on `article_family_id`, never on an individual PDF. This prevents near-duplicate tables from leaking across splits.

## Access tiers

Corpus papers are stratified as:

- `paper_only`;
- `public_code_restricted_data`;
- `public_replication`;
- `public_data_and_code`.

Missing or restricted data change **verification coverage**, not expected research-integrity risk.

## Copyright and artifact storage

The repository stores metadata, stable URLs, hashes, annotations, and reconstruction scripts.

A PDF/data/code artifact is copied into the repository only when redistribution rights are clear. Otherwise AuditBench records the canonical source URL and, when legally obtained for a run, its SHA-256. `redistributable_artifacts=False` is therefore normal and is not a benchmark failure.

## Stratification targets

A production certification split should be reported by at least:

- discipline: economics, psychology, management/organization, political science, sociology, education;
- reporting surface: prose, regression table, descriptive table, correlation table, appendix;
- access tier;
- detector family;
- publication year band;
- extraction path/parser family.

The primary safety metric remains the paper-level false hard-alert rate with an exact one-sided confidence bound. Claim-level metrics are diagnostic and must not replace the paper-level safety gate.

## Corpus admission checklist

A paper enters the locked benchmark only when:

1. bibliographic identity and article family are resolved;
2. access tier and redistribution status are recorded;
3. every included claim has precise provenance (page/table/row/column when available);
4. detector applicability has been independently reviewed;
5. natural positive/negative labels satisfy the adjudication rule;
6. controlled corruptions have immutable manifests;
7. the corpus manifest hash is frozen before final-test evaluation.

## Initial source strategy

Start from sources that already encourage transparent computational reproduction, including the AEA Data and Code Repository ecosystem and claim-level records from the Social Science Reproduction Platform. These are sampling frames, not automatic truth labels: every Veritas benchmark label still requires the corpus protocol above.
