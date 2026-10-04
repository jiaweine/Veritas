# Release process

Veritas separates **software release readiness** from **scientific-validation authority**. A green build, a GitHub Release, or an installable wheel does not certify real-paper detector performance and does not close evidence milestones that require independent human review or external historical trust.

## Release gates

Before creating a release tag:

1. Merge release changes into `main`; do not release from an unmerged feature branch.
2. Update `pyproject.toml` to the intended semantic version and move the relevant `CHANGELOG.md` material into a level-2 section for that exact version, for example `## 0.14.1 — 2026-10-04`.
3. Require the normal repository CI and browser/stress workflows to be green on the exact release candidate commit.
4. Require the `package-release` artifact-smoke job to be green. It builds both wheel and sdist, checks package metadata, verifies all four console entry points, confirms critical Web/PWA assets are present, installs the wheel into a clean virtual environment, and runs every CLI's `--version` path.
5. Re-check `docs/REPOSITORY_COMPLETION.md` and the open evidence milestones. Release notes must not turn synthetic, benchmark-only, pilot, or unadjudicated evidence into a production-certification claim.
6. Create an immutable tag named exactly `vX.Y.Z`, where `X.Y.Z` exactly matches `[project].version` in `pyproject.toml`.

The tag workflow independently enforces the release candidate again. Before GitHub Release publication it requires both the package artifact smoke and a reusable invocation of the full repository CI on the exact tagged commit. It also enforces three identity conditions: the tag must match the package version, the changelog must contain the same version, and the tagged commit must already be contained in `main` history.

## Workflow dependency identity

Active workflows that continuously protect `main`, pull requests, release artifacts, browser acceptance, mobile typechecking, and Harness stress use third-party GitHub Actions only by immutable 40-character commit SHA. Human-readable major versions remain comments, not executable refs. `scripts/check_github_action_pins.py` and `tests/test_github_action_pins.py` fail if one of those active workflows reintroduces a movable external action ref.

The frozen `capture-v015-*` evidence workflows and the historical reproduction shakedown are intentionally outside that modernization list. Rewriting historical evidence workflow source after the fact would blur which workflow semantics belonged to earlier capture runs. Past evidence remains tied to its original repository commit and Actions run; future production-authority evidence must use separately precommitted and externally trusted workflow identity as required by the evidence protocol.

## Automated GitHub Release

Pushing a `v*` tag triggers `.github/workflows/package-release.yml`.

The workflow:

- runs the same wheel/sdist artifact smoke used on pull requests;
- invokes `.github/workflows/ci.yml` as a reusable `release-ci` gate on the exact tag commit, including Ruff, pytest, locked AuditBench, PDF regression/geometry, adversarial fail-closed, and the existing real-PDF probes;
- does not allow the GitHub Release job to start until both artifact smoke and exact-tag CI have succeeded;
- binds the artifact-smoke report and artifact name to the actual source commit SHA rather than a pull-request merge-ref SHA;
- rejects a tag whose version differs from `pyproject.toml`;
- rejects a tag without a matching versioned `CHANGELOG.md` section;
- rejects a tagged commit that is not in `main` history;
- rebuilds the exact tagged source before publication;
- re-runs the artifact contract check on that rebuild;
- generates `SHA256SUMS.txt` for the wheel and source distribution;
- creates one GitHub Release containing the validated wheel, source distribution, and SHA-256 manifest.

`ci.yml` continues to run on pull requests and branch pushes. Direct tag-triggered CI is intentionally routed through `package-release` instead, so publication has an explicit dependency on that exact CI result rather than racing an independent workflow run.

Published GitHub Release assets are treated as immutable. If a release for the tag already exists, the workflow fails instead of overwriting or clobbering its assets.

Release notes explicitly preserve the authority boundary: a software package release is not a production scientific-validation certificate.

## Repository hosting controls

Branch protection and repository rulesets live in GitHub hosting configuration rather than in the source tree. For a governed release, `main` should require pull requests and the relevant required checks, and should reject force-pushes and deletion. Source-controlled CI/release gates remain independently valuable, but they cannot substitute for host-level protection against an authorized direct push.

## Package publication scope

The repository currently automates **GitHub Release artifacts only**. It does not publish to PyPI and does not assume package-index credentials or trusted-publishing configuration that are not present in the repository.

If PyPI publication is added later, it should be a separate job with environment protection / trusted publishing, should consume the already validated release artifacts, and must not weaken the tag/version/main-history/changelog, exact-tag CI, or evidence-authority gates above.

## Versioning and v0.15 evidence artifacts

The `benchmark/extraction/*v0.15*` files and `capture-v015-*` workflows describe the frozen real-paper evidence pilot. That evidence protocol version is not itself the Python package version and must not be used as a reason to bump or certify the software package.

The current v0.15 evidence path remains explicitly non-production until its independent-review, adjudication, DEVELOPMENT-only calibration, untouched TEST, external trust, and cold-verification requirements are actually satisfied.

## Failed release handling

Do not move an existing release tag to different source bytes and do not replace assets on an existing GitHub Release. Fix the problem on `main`, increment the version as appropriate, update the changelog, re-run the release gates, and create a new tag. This keeps the mapping from release tag to source tree and attached hashes auditable.
