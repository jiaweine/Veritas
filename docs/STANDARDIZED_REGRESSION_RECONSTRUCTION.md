# Standardized Regression Reconstruction

Veritas can cross-check a reported standardized OLS regression against a reported correlation matrix without access to raw data.

## Identity

For a standardized linear OLS regression using the same observations and exactly the same predictor set as the reported correlation matrix,

`R_xx beta = r_xy`.

The detector is applicable only when all three semantic conditions are independently established:

- the coefficients are standardized OLS coefficients for which the identity applies;
- the regression and correlation matrix use the same sample;
- the predictor set is complete and matches the reconstructed system.

If any condition is uncertain, the result is `UNVERIFIABLE`.

## Rounding uncertainty

Every displayed correlation and beta is represented by its rounding-compatible interval. Veritas does not plug the printed midpoint into `R_xx^-1 r_xy` and call a mismatch an error.

## Stage 1: constructive midpoint witness

The detector first builds the midpoint correlation matrix from the reported intervals. If this matrix is PSD, solves

`R_xx beta = r_xy`,

and the implied beta vector lies inside every reported beta interval, then an explicit compatible witness has been constructed. The check can `PASS` without invoking a conic optimizer.

Failure to find this witness is not evidence of inconsistency; many valid systems need a non-midpoint completion.

## Stage 2: PSD-constrained McCormick outer relaxation

The exact uncertain system contains bilinear terms `R_ij * beta_j`. For every bilinear term `w = x y` with known bounds, Veritas introduces `w` and the four McCormick envelope inequalities. These form an outer convex relaxation of the true bilinear graph.

The candidate correlation matrix is simultaneously constrained to be positive semidefinite with diagonal equal to one and every required off-diagonal cell inside its reported rounding interval.

Because the relaxed feasible set contains the exact feasible set:

- relaxed infeasibility implies exact infeasibility, subject to numerical-solver validity;
- relaxed feasibility does **not** prove exact feasibility.

Therefore Veritas never turns a merely feasible relaxation into `PASS`.

## Stage 3: piecewise tightening

If the outer relaxation is feasible but does not produce an independently verified exact witness, Veritas splits the widest standardized-beta interval and resolves both boxes recursively. This is a piecewise McCormick tightening strategy.

A reported incompatibility requires every box covering the original beta intervals to be explicitly infeasible. Any unresolved node, solver ambiguity, inaccurate solve, or exhausted partition budget yields `UNVERIFIABLE`.

## Numerical governance

The SDP backend is currently validated only with `SCS==3.2.11`. The runtime version is checked before solver invocation. A different SCS version disables the solver-based part of the detector instead of silently changing results.

Solver-based infeasibility is capped at E2 until the detector passes AuditBench hard-alert certification. Solver versions are part of the audit protocol lock.

## Interpretation

An E2 result means:

> Under the verified standardized-OLS relationship and the modeled rounding intervals, even a convex outer relaxation could not reconcile the published correlation matrix and standardized coefficients.

It does not imply fabrication, falsification, or author intent.
