# Claim graph and estimand identity contract (v0.12)

Veritas v0.12 treats empirical-claim identity as a separate evidence problem. A numerical detector being correct about a table cell does not prove that the cell supports, contradicts, or even refers to a sentence-level claim elsewhere in the paper.

## Graph chain

`StatisticalClaimGraph` can represent the artifact-derived chain

`Claim -> Estimate -> Sample -> Data -> Code -> Assumption`

with publication/artifact provenance on every node and edge.

- `ClaimNode` stores publication claim text and source span.
- `StatisticalObjectNode` remains the estimate/statistical-object node.
- `EvidenceNode` adds first-class `sample`, `data`, `code`, `assumption`, and `design` nodes.
- `ClaimEdge.sources` records the source locations used to justify a link.
- `ClaimEdge.extraction_confidence` and `ClaimEdge.identity_confidence` travel with the link; `effective_confidence` is the conservative minimum of link, extraction, and identity confidence.

The graph serializer remains backward-compatible with v0.11 graphs that contain only artifacts, claims, statistical objects, and the original edge fields.

## Estimand identity

`EstimandIdentity` normalizes the dimensions that must not be silently conflated across publication locations:

- outcome
- treatment/exposure
- scale transformation
- optional population
- optional time horizon
- optional unit

Scale transformations are explicit enums. In particular, percent and percentage-point effects are different identities, as are probability, log-odds, and odds-ratio scales. Unknown transformations never become implicit matches.

`compare_estimand_identity()` is deterministic and deliberately non-fuzzy. Outcome, treatment, and transformation form the core identity and carry 0.90 of the score. Optional population and time-horizon identity account for the remaining 0.10 when both sides provide them. A conflict is not repaired by lexical similarity or detector output.

## Cross-location E3 gate

Object-level numerical detectors may still produce their ordinary findings. To assert that an E3+ finding at one publication location bears on a claim at another location, callers use `bind_cross_location_claim_findings()`.

That boundary fails closed unless:

1. outcome, treatment, and scale transformation match exactly after normalization;
2. identity confidence meets the configured threshold (0.90 by default);
3. the conservative effective confidence, including extraction and matcher uncertainty, meets the threshold (0.90 by default);
4. the aligned estimate object is the same object referenced by every E3+ finding being bound.

Successful bindings write both claim and estimate source locations plus identity/extraction confidence into `finding.evidence["claim_identity_binding"]`.

Lower-grade object-level signals are not upgraded merely because a candidate claim link exists.

## Identity benchmark

`evaluate_claim_identity()` scores accepted claim/estimate links independently from detector correctness. It reports link precision, recall, F1, and exact estimand-identity accuracy. A detector may be numerically correct while the claim identity is wrong, and the benchmark records that as an identity error rather than a detector success.

## Scope

This is an implemented claim-graph and identity-control substrate. It does not claim that arbitrary papers can already be parsed into perfect claim graphs without held-out real-paper evaluation. Production hard-finding authority remains governed separately by the existing calibration/certification system.
