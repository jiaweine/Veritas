# v0.11 real-paper reproduction benchmark

This benchmark is an experimental evidence track. It is not production certification and it does not change paper-only detector authority.

## Goal

Measure whether a frozen implementation can recover publication-visible empirical results **without fitting code to the paper's numeric answers**. The benchmark keeps three questions separate:

1. Can the authors' own package rerun under a pinned environment?
2. Can an independent implementation recover the same claim from paper-grounded methods plus data?
3. When the answer differs, can an independent reviewer attribute the discrepancy without treating the coding agent as the judge?

A paper may pass one question and fail or remain unverifiable on another.

## Benchmark gates

### Gate A — artifact and legal identity

Pin the article version, data files, schemas, and (for author-package reruns only) original code. Hash every artifact. Verify file-level access, license, and model-egress policy before any remote agent sees data. A repository landing page is not enough evidence of artifact identity.

### Gate B — blinded method specification

Two independent reviewers build or review a design-specific `MethodSpecification`. It must bind to a declared reproduction contract such as `regression_v1`, `did_v1`, `iv_v1`, or `rdd_v1`. Missing required choices are materialized as missing and block execution; the agent may not invent them.

The model-visible projection contains semantic method choices only. Publication text quotes, page/table/row locators, paper URLs, repository URLs, author code, output artifacts, and reported outcomes remain outside the agent workspace.

### Gate C — target seal

Independently extract the publication cells to be tested and define their claim identity and materiality. Review them before execution, then create the target commitment. Numeric reported values remain orchestrator-only until the final workspace is frozen.

Candidate-selection manifests contain no numeric paper targets. This prevents an engineering manifest from quietly becoming an answer key.

### Gate D — blind CodeAgent implementation

The independent agent runs offline. Network access and numeric target-distance feedback are forbidden. Only leak-reviewed `raw_data`, `analysis_data`, `data_dictionary`, and `schema` artifacts may be mounted.

Multiple attempts are allowed only if every attempt is blind to the target values. Selection among attempts may use execution validity and method-fidelity checks, never closeness to the paper result.

### Gate E — frozen execution

Freeze generated code, workspace, runtime/container, package versions, input hashes, sandbox policy, stdout/stderr, and output hashes. Reproduction output must follow the strict target JSON contract. A successful process exit is not evidence of result agreement.

### Gate F — deterministic unseal and comparison

After the workspace is frozen, unseal the paper targets. Compare at cell level using the paper's rounding interval or inequality semantics, then summarize by `claim_id`:

- `MATCH`: every sealed cell for the claim matches;
- `MISMATCH`: at least one sealed cell numerically disagrees;
- `PARTIAL`: some sealed cells match but others are missing;
- `UNVERIFIABLE`: all sealed cells are missing.

Do not replace these identities with one aggregate RMSE or similarity score.

### Gate G — discrepancy attribution and evidence promotion

A numerical mismatch from an experimental CodeAgent is at most E1. E4 requires independently verified artifact identity, method fidelity, frozen execution provenance, target identity/comparison rules, and either an author-package rerun or an independently adjudicated reimplementation.

A successful match is positive evidence for the tested claim under the tested artifacts and environment; it is not proof that the paper is globally correct.

## Contamination control

No browsing is necessary but not sufficient for independence. Published papers and replication repositories may have appeared in model training data. For benchmark scoring, record a contamination-risk assessment separately from ordinary sandbox isolation.

A replication package's publication date is **not** a valid proxy for paper novelty. A package can be newly deposited while the paper, working paper, conference draft, tables, or code have been public for years. Agent-independence eligibility therefore needs the first-public-release history of the paper and relevant data/code, not merely the current repository version date.

Use older or widely available replication packages primarily to shake down the pipeline. For CodeAgent capability estimates, prefer papers and data whose first public release is demonstrably after the evaluated model's documented training cutoff, or use an externally held-out/non-public evaluation corpus with appropriate data governance. When neither condition can be established, report contamination risk as unknown and keep the run out of the independence score.

Remove explicit paper identity from the model-visible task wherever implementation does not require it, and never expose paper/repository URLs. Variable aliases or stronger schema identity blinding may be added only after verifying that the transformation preserves the estimand and method contract.

Because model-memory contamination cannot be proven absent from runtime controls alone, do not describe a blind CodeAgent match as an "independent replication" solely because the network was disabled.

## First-candidate strategy

`benchmark/reproduction/candidates_v0.11.json` currently contains **engineering candidates, not a clean CodeAgent-independence benchmark**:

- the 2019 Tanzania education package is useful for pipeline and author-package shakedown, but its age and public visibility make it a weak benchmark of model independence;
- `Polluted IPOs` has a convenient openICPSR V1 package published in 2026, but public working-paper/conference versions existed by 2022. Package recency therefore does not make the paper contamination-reduced. It remains useful for version-pinning, artifact, author-package, and blind-workflow engineering once the exact paper-to-package mapping is locked;
- other recent-package candidates remain blocked until their first-public-release history is established relative to the evaluated model's documented training cutoff.

A genuinely contamination-reduced first benchmark should be selected only after this temporal/holdout gate is satisfied. No candidate becomes benchmark gold or TEST evidence merely because it appears in the sampling manifest.

## Research basis

The design is consistent with two useful precedents while retaining stricter Veritas evidence promotion:

- OpenAI PaperBench decomposes full-paper replication into independently gradable outcomes and evaluates executable submissions rather than prose claims: https://openai.com/index/paperbench/
- Kohler et al. (2026), *Read the Paper, Write the Code*, studies social-science reimplementation from structured methods plus original data under information isolation, with deterministic cell-level comparison and discrepancy attribution: https://arxiv.org/abs/2604.21965

Veritas additionally separates author-package reproduction from independent reimplementation and caps unaudited agent mismatches below hard integrity authority.
