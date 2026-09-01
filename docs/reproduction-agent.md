# Code-agent reproduction audit

Veritas treats computational reproduction as a separate evidence chain from paper-only consistency auditing.
A coding agent is an implementation tool, not an integrity judge.

## Questions the reproduction layer answers

1. **Author-package reproduction** — when author code and data are available, can the supplied package regenerate the reported computational results under a pinned environment?
2. **Independent method reimplementation** — when data are available, can an independent implementation derived only from the publication-grounded method specification recover the same results?
3. **Discrepancy attribution** — when results differ, is the most plausible source data preprocessing, sample selection, variable construction, estimator choice, inference, randomness, environment, method underspecification, or agent implementation?

These questions must not be collapsed into a single "reproducible" score.

## Evidence-availability rule

No data means computational reproduction is `UNVERIFIABLE`, not suspicious. The CodeAgent path should activate only when the necessary data artifacts exist. Missing author code still allows an independent reimplementation if the method specification and data are sufficient.

## Two execution modes

### 1. Author-code reproduction

The original analysis code is the object being tested. The default action is to execute it unchanged. A CodeAgent may repair environment, dependency, path, or compatibility issues, but every patch is hashed and preserved. Silent changes to estimators, samples, transformations, model formulas, or inference are forbidden.

A zero-patch run must still carry an explicit empty-patch hash so that "no code modification" is an auditable fact.

### 2. Independent reimplementation

The CodeAgent receives:

- a structured `MethodSpecification` grounded in publication-visible text;
- data artifacts and schemas;
- blind target descriptors such as `claim_id + metric`;
- execution constraints.

It does **not** receive:

- the paper's numeric target values;
- the original author code;
- numeric distance-to-target feedback while iterating.

The paper's target values are bound before execution by a SHA-256 commitment. The generated code and workspace are frozen before the target values are unsealed for deterministic comparison. After unsealing, Veritas recomputes the full target-set commitment and requires it to match the commitment embedded in the locked task before an attested report can be promoted. This blocks both result-fitting and post-run target substitution.

## MethodSpecification

The schema is statistical-object based rather than discipline based. Required fields vary by design, but common fields include:

- outcome and treatment/exposure definitions;
- sample inclusion/exclusion rules;
- data transformations and constructed variables;
- estimator/model family;
- controls and interactions;
- fixed effects;
- weights;
- clustering/inference method and degrees of freedom where applicable;
- time/event window and comparison group for panel/DID designs;
- instrument/first stage for IV;
- cutoff, polynomial/order, kernel and bandwidth for RDD;
- scale construction, missing-data handling and weighting for surveys;
- random seeds or stochastic procedures when material.

A required field that is missing or below the calibrated extraction-confidence threshold blocks independent computational reproduction. The correct state is method-underspecified / unverifiable; the agent must not invent the missing choice and then treat the resulting mismatch as evidence against the paper.

## Execution boundary

Generated or supplied research code is untrusted input. Production execution should use a sandbox with:

- network disabled by default;
- read-only input mounts;
- no host filesystem access;
- no credentials;
- CPU, memory and wall-clock limits;
- pinned language/package environments;
- hashed container/environment identity;
- stdout/stderr and output artifact provenance;
- a frozen final workspace hash before result comparison.

The core Veritas package keeps author-code and independent-agent adapter boundaries distinct. A full internal `CodeAgentTask` may be consumed only through the author-code backend boundary. Independent reimplementation backends consume the leak-safe `AgentTaskView` through `BlindCodeAgentBackend` and the canonical blind dispatch path. Codex, SWE-agent, or another coding backend can implement those adapters without changing the evidence rules.

### Blind agent dispatch boundary

Independent reimplementation has an additional information-security boundary. An agent adapter must not consume the full internal `CodeAgentTask` directly. The supported dispatch path first validates artifact egress policy, then projects the task into a leak-safe `AgentTaskView`, calls the backend, and finally validates that the returned proposal is bound to the original locked task.

For independent reimplementation, the model-visible artifact roles are deliberately narrow: `raw_data`, `analysis_data`, `data_dictionary`, and `schema`. Paper PDFs, reported-result files, author output, replication packages, and other undeclared roles are rejected at the agent-view boundary rather than silently exposed.

Upstream artifact URIs are also excluded from `AgentTaskView`. A repository or deposit URL that appears to identify only a data file can colocate original code, tables, or numeric targets. The orchestrator therefore mounts approved artifacts by opaque `artifact_id`/hash outside the model-visible task payload. This preserves artifact provenance for Veritas while preventing the coding agent from following a source URL to the answer.

These restrictions are separate from data-sensitivity policy. Remote dispatch still requires explicit model-egress authorization for every public artifact; restricted data stays local unless an approved confidential-compute policy applies.

## Comparing effects with the paper

Comparison is deterministic and claim/display-item level. Printed values are not compared naively: equality uses the paper's feasible rounding interval, and censored reports such as `p < 0.001` are treated as inequalities.

The first comparison layer records:

- matched cells;
- mismatched cells;
- missing outputs;
- material mismatches affecting main empirical claims.

Every reproduced non-missing comparison also retains the SHA-256 identity of the output artifact from which its value came. An E4-capable attested report accepts that cell only when the referenced hash is one of the output artifacts recorded by the frozen execution attestation. A numerically plausible cell from another run or hand-created file therefore cannot be attached to an otherwise valid execution chain.

Method-specific comparators should then compare structured statistical objects rather than only flat cells. Examples:

- OLS/logit: coefficient, SE, test statistic, p/CI, N, fixed effects and inference identity;
- DID/event study: target estimand, event-time ATT vector, comparison group, sample and inference;
- IV: second-stage estimate, first-stage/strength diagnostics and inference;
- RDD: cutoff estimate, bandwidth, polynomial/kernel choices and inference;
- survey/SEM: scale construction, model coefficients, fit indices and missing-data handling;
- meta-analysis: study set, effect-size construction, heterogeneity statistics and pooled effect.

A single aggregate RMSE is insufficient: a run can be numerically close while implementing the wrong estimand, or numerically different only because the paper printed a rounded value.

## Real-package readiness and sealed post-run comparison

Execution readiness and evidence-promotion readiness are separate states. A package can be legally and technically runnable in an isolated sandbox while still being ineligible for production evidence because target adjudication or independent method-fidelity review is incomplete. Conversely, a public repository listing is not enough to mark a package executable: artifact-level terms, version identity, hashes, and runtime requirements still have to be pinned.

Paper and replication-package versions must be pinned as a pair. A later package release must not silently replace the package that corresponds to the selected publication version when the reported result or calibration changed between releases.

For sealed comparison, the numeric paper target remains outside the repository and agent workspace. Before execution, Veritas stores only a target commitment plus an answer-free binding that says how to locate the reproduced value in the frozen output, for example an exact CSV row selector and value column. After the sandbox run is frozen, `reproduction_ingest`:

1. opens the private target and recomputes its commitment;
2. verifies the pinned package commit, source manifest, immutable runtime, execution security properties, and actual output bytes;
3. extracts exactly one reproduced value from the bound output location;
4. calls the normal Veritas rounding-aware comparator;
5. emits an answer-free certificate containing only the decision and provenance hashes, not the reported or reproduced numeric values.

A target commitment mismatch, changed output bytes, ambiguous output row, or disagreement between an attested value and the bound output fails closed. The descriptive certificate cannot enable production or E4 authority on its own.

The first v0.11 engineering shakedown follows this flow on the public Model-LB author package. The public preprint is deliberately paired with package `v1.3.1`, not the later `v2.x` package state; the exact author package is rerun in a network-disabled, read-only sandbox using an immutable Python base image and an exact dependency lock. The discovery run and precommitted frozen rerun produced identical source-manifest, environment, and output hashes, and the sealed target comparison returned `MATCH`. The case remains non-production and is prohibited from agent-independence scoring because independent target adjudication and method-fidelity review are still incomplete. This is a pipeline shakedown, not a global reliability judgment about the paper.

## Evidence promotion

A CodeAgent mismatch is not automatically E4.

`E4 REPRODUCTION_CONTRADICTION` is permitted only when all of the following are verified:

1. input artifact identity;
2. method fidelity of the executed implementation;
3. sandbox execution/provenance;
4. the unsealed target set exactly matches the task's pre-run target commitment;
5. every reproduced comparison is bound to an output artifact from that attested execution;
6. authority matches the execution mode: author-package authority requires an author-code task, while independent-adjudicated authority requires an independent-reimplementation task;
7. either an author-package rerun or an independently adjudicated reimplementation.

The ordinary `build_reproduction_report()` path is descriptive only and cannot self-promote to E4 by accepting caller-supplied verification booleans. Hard reproduction authority is available only through the attested builder after the mode, target commitment, method fidelity, artifact identity, execution, and comparison-output bindings have all been validated.

A fully attested report also carries an immutable `ReproductionEvidenceBinding` rather than discarding provenance after construction. It records the locked task and method-spec hashes, pre-run target commitment, executed code hash, frozen workspace hash, environment and sandbox-policy hashes, and the exact input/output artifact hash sets. The descriptive report path leaves this binding absent. This makes a saved E4-capable report independently traceable back to the artifacts and execution that justified it.

An experimental agent mismatch is capped at `E1 WEAK_SIGNAL`, even when the numerical difference is large. This prevents agent bugs from being misattributed to authors.

A successful match is also not proof that a paper is globally reliable. It is positive evidence only for the tested claims under the tested artifacts and environment.

## Research basis

The architecture borrows three useful ideas from recent agent-replication work while adapting them to social-science integrity auditing:

- OpenAI PaperBench (2025): decompose end-to-end replication into fine-grained, independently gradable outcomes rather than one opaque success score — https://openai.com/index/paperbench/
- Kohler et al., *Read the Paper, Write the Code: Agentic Reproduction of Social-Science Results* (2026): strict information isolation, independent reimplementation from paper methods plus data, deterministic cell-level comparisons, and discrepancy attribution — https://arxiv.org/abs/2604.21965
- Nguyen et al., *ReplicatorBench* (2026): evaluate resource retrieval, experiment design/execution, and interpretation as separate stages, including both replicable and non-replicable claims — https://arxiv.org/abs/2602.11354

The Veritas-specific addition is evidence promotion: the agent is never the final judge, and reproduction failures are capped by verified provenance and method-fidelity gates before they can contribute to an integrity finding.
