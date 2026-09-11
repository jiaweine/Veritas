# Discrete Summary Forensics

Veritas v0.3 generalizes GRIM/GRIMMER-style consistency checking into an explicit finite-support feasibility problem.

## Why not call GRIM/GRIMMER directly?

GRIM is an important methodological precedent for checking whether a rounded mean is compatible with an integer-valued sample and a reported N. GRIMMER extends this idea to variability. Veritas uses these methods as anchors, but it does not delegate high-severity decisions to an external implementation.

As of the 2026-08-31 methodology snapshot, the current `scrutiny` GRIMMER documentation explicitly warns that its `items` argument contains a bug. Veritas therefore treats composite-scale support as an explicit modeling problem rather than assuming an `items` transformation is correct.

## Applicability gates

The detector runs only if all of the following are established:

- the statistic-specific sample size N is verified;
- the variable's complete finite support is verified;
- the summary is unweighted (`weighted=False`);
- the mean is reported as an equality;
- if an SD is checked, its definition is known as sample or population SD.

If these conditions are not established, the result is `UNVERIFIABLE`, not suspicious.

## Integer feasibility formulation

Let the verified support be

`x_1, ..., x_K`

and let `c_k` be the number of observations at support value `x_k`.

The variables satisfy

`c_k in Z_{>=0}`

and

`sum_k c_k = N`.

Support values are converted to an exact decimal lattice with scale `D`, producing integer values `y_k = D x_k`.

### Mean

For a reported rounded mean, Veritas constructs the conservative rounding-compatible interval `[m_lo, m_hi]` and imposes

`N D m_lo <= sum_k y_k c_k <= N D m_hi`.

This is a mixed-integer linear feasibility problem and is solved with `scipy.optimize.milp` / HiGHS.

### Mean + SD

Let

`S = sum_k y_k c_k`

and

`Q = sum_k y_k^2 c_k`.

For each integer value of `S` permitted by the rounded mean, Veritas converts the rounded SD interval into linear bounds on `Q`.

For sample SD:

`Q - S^2/N = (N - 1) D^2 s^2`.

For population SD:

`Q - S^2/N = N D^2 s^2`.

Because `S` is fixed within each subproblem, the SD constraint is linear in the integer count variables. This avoids non-convex MIQP heuristics.

## Solver uncertainty

A solver timeout, numerical failure, or ambiguous status is never treated as infeasibility.

- feasible + independently re-verified integer witness -> `PASS`;
- every admissible subproblem explicitly infeasible -> finding;
- any unresolved admissible subproblem -> `UNVERIFIABLE`.

Returned witnesses are re-rounded to integer counts and checked using integer arithmetic before acceptance.

## Severity ceiling

The detector is experimental. Even mathematically infeasible results are capped at E2 until the detector passes the locked AuditBench hard-alert certification policy. The evidence record states this ceiling explicitly.

This separates two questions:

1. Is the finite-support model mathematically incompatible with the reported summaries?
2. Has the detector been validated strongly enough to produce a production E3 finding across real reporting styles?

The first can be proven per case. The second requires benchmark evidence.
