# Reproducibility artifacts contract (v0.13)

Veritas v0.13 adds an executable reproducibility-artifact substrate around the fail-closed reproduction control plane. The implementation separates **runner isolation**, **environment identity**, **data/code provenance**, **publication-object matching**, and **E4 finding construction** so that no single unverified layer can silently grant hard reproduction authority.

## Isolated R and Python runners

`ContainerIsolationBackend` builds and, when a Docker-compatible OCI runtime is available, executes a locked container command.

The command contract requires:

- an image pinned by an explicit `@sha256:` digest;
- `--network none`;
- a read-only container root filesystem;
- all Linux capabilities dropped;
- `no-new-privileges`;
- bounded CPU, memory, process count, and wall time;
- the source/replication package mounted read-only at `/input`;
- a separate writable `/output` mount;
- temporary writable filesystems only at `/tmp` and `/work`;
- no arbitrary host environment forwarding.

Python jobs run `python /input/<entrypoint>`. R jobs run `Rscript --vanilla /input/<entrypoint>`. The backend hashes the source tree before and after execution and rejects a run if the supposedly read-only input tree changed.

`SandboxPolicy(network_disabled=False)` or `SandboxPolicy(read_only_inputs=False)` is rejected before command construction.

The repository CI validates this isolation **command contract**. Actual container execution additionally requires a compatible container runtime and daemon on the host; repository tests do not pretend that an unavailable host runtime has been certified.

## Environment and dependency capture

`DependencyLock` binds the exact dependency-lock file bytes. `EnvironmentSnapshot` binds:

- runtime family and version;
- host/runtime platform descriptor;
- pinned image reference;
- dependency-lock SHA-256;
- normalized package-inventory SHA-256 and count.

`capture_python_environment()` can inventory the current Python environment. `build_environment_snapshot()` provides the same stable contract for R and licensed Stata runtimes once their package inventory has been collected by the executor.

Changing the lock bytes, runtime version, image reference, or package inventory changes the environment identity.

## Optional licensed Stata adapter

`ReplicationRuntime.STATA` is implemented as an optional adapter. A Stata runner specification fails closed unless `stata_license_authorized=True` is explicitly supplied. This flag is an authorization input to the adapter, not proof of a license by itself; deployment remains responsible for providing a legally licensed runtime image.

## Processed-data and code provenance

`ReproductionProvenanceGraph` represents raw data, analysis data, code, and generated outputs as immutable SHA-256-identified artifacts. `ProvenanceTransform` binds each transformation to:

- one code artifact;
- one or more input artifacts;
- one or more output artifacts;
- the exact environment snapshot SHA-256.

The graph rejects unknown artifacts, non-code transform executors, multiple producers for one output, and cycles. A generated table/figure/output is considered provenance-complete only when its ancestor chain contains both code and data.

## Generated table and figure matching

`match_generated_table()` compares a generated table with a publication table signature only after row and column identities match exactly. Numeric cells use Veritas reporting semantics:

- equality cells use the reported rounding interval;
- `<`, `<=`, `>`, and `>=` cells preserve their comparison operator;
- missing generated cells remain mismatches rather than being imputed.

`match_generated_figure()` requires exact panel identity and a precomputed semantic data-series SHA-256. Pixel similarity alone is not treated as evidence that a generated figure represents the same statistical object.

Both match paths bind publication and generated artifact identities.

## Canonical E4 reproduction finding path

The public `build_attested_reproduction_e4_check()` API does **not** accept a caller-constructed `ReproductionReport`. It takes the locked task, sealed targets, CodeAgent proposal, sandbox policy, execution attestation, independent method-fidelity attestation, independent artifact-identity attestation, and comparison evidence, then invokes the canonical fully-attested report builder internally.

That existing authority boundary revalidates target commitments, actor separation, frozen execution, method fidelity, artifact identity, output hashes, finite numeric values, and canonical Veritas comparisons. A forged status, custom tolerance result, hidden numeric channel, or unbound output cannot be promoted through the v0.13 audit constructor.

A fully attested mismatch can produce an E4 `REPRODUCTION_CONTRADICTION` finding. The finding stores immutable evidence hashes, target identifiers, comparison statuses, agreement counts, authority, and root-cause classification, but deliberately does not copy reported or reproduced numeric answers into the finding payload.

A fully attested match produces a PASS check. Partial or missing comparisons remain REVIEW/UNVERIFIABLE rather than becoming hard findings.

## Authority and deployment scope

These components implement the v0.13 reproducibility-artifact software substrate. They do not, by themselves:

- certify that a particular deployment host provides the required OCI isolation;
- prove that an optional Stata runtime is licensed;
- certify arbitrary author replication packages;
- replace independent artifact/method review;
- production-certify E4 findings.

Production authority remains governed by the repository's separate held-out certification and governance requirements.
