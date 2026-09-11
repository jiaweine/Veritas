# Extraction execution attestation archive

`ExtractionExecutionAttestation` is a repository-side, non-production record that binds one exact threshold run to the frozen execution context. It is useful as an independently archived run record, but it is **not** an authority shortcut: the cold verifier still reconstructs execution evidence from the primary prediction artifact, release bundle, split manifest derivation, threshold grid, and execution plan instead of trusting this JSON as an input summary.

## Build one attestation per threshold run

After `scripts/run_extraction_evidence_threshold.py` has produced the exact canonical prediction artifact, build the corresponding archive record:

```bash
python scripts/build_extraction_execution_attestation.py \
  --execution-plan benchmark/extraction/extraction_execution_plan_v0.15.json \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --target-manifest evidence/splits/development-target-manifest.json \
  --prediction-artifact evidence/predictions/development/nc-005.json \
  --execution-id '<independently-recorded-execution-id>' \
  --threshold-id nc-005 \
  --output evidence/attestations/development/nc-005.json
```

Repeat this for every precommitted DEVELOPMENT and TEST threshold run.

The builder deliberately does **not** accept a caller-supplied threshold number. `--threshold-id` must exist in the frozen evidence-plan grid, and the threshold value is recovered from that precommitment. The prediction artifact must use the exact canonical JSON byte contract, and its target IDs must exactly equal the derived split target manifest membership.

The resulting attestation binds:

- execution-plan semantic SHA-256;
- DEVELOPMENT or TEST split;
- precommitted threshold ID and value;
- derived split target-manifest semantic SHA-256;
- exact prediction-artifact byte SHA-256;
- prediction semantic SHA-256;
- successful exit status;
- network-disabled, read-only-source, and no-credentials declarations;
- `production_authorized=false`.

The command prints both the attestation's canonical semantic SHA-256 and the exact written JSON-file SHA-256. Archive both identities when the file is transferred to the independent evidence channel.

## What this record does not prove

A structurally valid attestation does not prove that an external runner actually enforced network isolation, mounted the source read-only, withheld credentials, existed before TEST, or was controlled by an independent institution. Those are external provenance/governance facts and must be supported by the separately precommitted trust policy, signed provenance, historical archive, and independently selected expected run context.

The attestation is therefore not accepted as a trusted cold-verification input. `rebuild_attested_extraction_evidence_release_receipt_from_archive()` reopens the canonical prediction artifacts, recomputes benchmark observations, re-derives DEVELOPMENT threshold selection and the TEST lock, and rebuilds execution evidence itself. If an archived attestation disagrees with that reconstruction, the reconstruction remains authoritative and the mismatch is evidence that the archive record is inconsistent.

This archive path never grants production authority.
