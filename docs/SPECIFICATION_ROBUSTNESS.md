# Specification robustness: constrained multiverse, not significance voting

Many empirical conclusions depend on defensible analytic choices. The 2025 multi-analyst study in *Nature* found substantial dispersion across independent reanalyses of the same social/behavioural claims, reinforcing the need to represent analytical uncertainty directly rather than assuming the published path is unique.

Veritas does **not** treat `p < .05` frequency across arbitrary models as a fraud detector. Specification analysis is a robustness layer.

## Specification graph

A `SpecificationSpace` declares named dimensions such as:

- sample inclusion rule;
- outcome transformation;
- control set;
- fixed-effects structure;
- functional form;
- treatment timing/window;
- clustering/inference choice;
- bandwidth or trimming rule.

Only theoretically justified choices belong in the space. Explicit incompatibility constraints prevent nonsensical combinations. The entire space receives a stable SHA-256 hash and should be frozen before the final robustness run.

## Non-redundancy / equivalence weighting

A naive multiverse can be gamed by adding many tiny variants of one model. Veritas assigns equal total weight to each declared equivalence group, then divides that weight among near-duplicate specifications inside the group. This is a practical implementation of the specification-curve principle that the model set should be theoretically valid and non-redundant.

## Reported robustness quantities

The first implementation reports:

- equivalence-balanced median and 5th/95th percentiles of the estimate;
- equivalence-balanced mean and dispersion;
- sign stability relative to the original estimate (or multiverse median if no original is marked);
- stability above a user-defined smallest effect size of interest (SESOI);
- the original estimate's percentile within the admissible multiverse;
- which analytic dimension changes the average estimate most.

These are descriptive robustness quantities. They do not by themselves imply selective reporting or misconduct.

## Next inferential layer

For data-enabled audits, the next version should add joint/null inference following specification-curve methods, plus design-specific resampling appropriate to clustering, randomization, panel dependence, or RD/DiD structure. The resampling method itself must be part of the locked protocol.
