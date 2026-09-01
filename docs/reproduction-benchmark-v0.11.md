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

Use older, well-known replication packages primarily to shake down the pipeline. Prefer newer or otherwise contamination-reduced papers for CodeAgent capability estimates. Remove explicit paper identity from the model-visible task wherever implementation does not require it, and never expose paper/repository URLs. Variable aliases or other stronger identity blinding may be added after the first real benchmark demonstrates that they do not change the estimand.

Because model-memory contamination cannot be proven absent from runtime controls alone, do not describe a blind CodeAgent match as an "independent replication" solely because the network was disabled.

## First-candidate strategy

`benchmark/reproduction/candidates_v0.11.json` deliberately separates two uses:

- the 2019 Tanzania education package is useful for pipeline and author-package shakedown, but its age and public visibility make it a weak first benchmark of model independence;
- the 2026 `Polluted IPOs` package is a preferred recent candidate once the exact paper/package versions, artifact permissions, one narrow claim, and a double-reviewed MethodSpecification are locked.

Neither candidate is benchmark gold yet. No candidate may become TEST evidence because it appears in this file.

## Research basis

The design is consistent with two useful precedents while retaining stricter Veritas evidence promotion:

- OpenAI PaperBench decomposes full-paper replication into independently gradable outcomes and evaluates executable submissions rather than prose claims: https://openai.com/index/paperbench/
- Kohler et al. (2026), *Read the Paper, Write the Code*, studies social-science reimplementation from structured methods plus original data under information isolation, with deterministic cell-level comparison and discrepancy attribution: https://arxiv.org/abs/2604.21965

Veritas additionally separates author-package reproduction from independent reimplementation and caps unaudited agent mismatches below hard integrity authority.
